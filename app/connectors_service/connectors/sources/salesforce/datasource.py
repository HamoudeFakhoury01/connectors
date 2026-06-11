#
# Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
# or more contributor license agreements. Licensed under the Elastic License 2.0;
# you may not use this file except in compliance with the Elastic License 2.0.
#

import os
from datetime import datetime
from functools import partial

import aiohttp
from connectors_sdk.logger import logger
from connectors_sdk.source import BaseDataSource, ConfigurableFieldValueError
from connectors_sdk.utils import (
    iso_utc,
)

from connectors.access_control import (
    ACCESS_CONTROL,
    es_access_control_query,
    prefix_identity,
)
from connectors.cleaning.encoding import EncodingFixer
from connectors.cleaning.footer import FooterStripper
from connectors.cleaning.pipeline import CleaningPipeline
from connectors.cleaning.politeness import PolitenessStripper
from connectors.cleaning.reply_chain import ReplyChainStripper
from connectors.cleaning.signature import SignatureStripper
from connectors.cleaning.url import UrlStripper
from connectors.sources.salesforce.client import SalesforceClient
from connectors.sources.salesforce.constants import (
    BASE_URL,
    RUNNING_FTEST,
    SALESFORCE_EMULATOR_HOST,
    STANDARD_SOBJECTS,
    WILDCARD,
)
from connectors.sources.salesforce.validator import SalesforceAdvancedRulesValidator


def _prefix_user(user):
    if user:
        return prefix_identity("user", user)


def _prefix_user_id(user_id):
    return prefix_identity("user_id", user_id)


def _prefix_email(email):
    return prefix_identity("email", email)


class SalesforceDocMapper:
    def __init__(self, base_url):
        self.base_url = base_url

    def map_content_document(self, content_document):
        content_version = content_document.get("LatestPublishedVersion", {}) or {}
        owner = content_document.get("Owner", {}) or {}
        created_by = content_document.get("CreatedBy", {}) or {}

        return {
            "_id": content_document.get("Id"),
            "content_size": content_document.get("ContentSize"),
            "created_at": content_document.get("CreatedDate"),
            "created_by": created_by.get("Name"),
            "created_by_email": created_by.get("Email"),
            "description": content_document.get("Description"),
            "file_extension": content_document.get("FileExtension"),
            "last_updated": content_document.get("LastModifiedDate"),
            "linked_ids": sorted(content_document.get("linked_ids")),
            "owner": owner.get("Name"),
            "owner_email": owner.get("Email"),
            "title": f"{content_document.get('Title')}.{content_document.get('FileExtension')}",
            "type": "content_document",
            "url": f"{self.base_url}/{content_document.get('Id')}",
            "version_number": content_version.get("VersionNumber"),
            "version_url": f"{self.base_url}/{content_version.get('Id')}",
        }

    def map_salesforce_objects(self, _object):
        def _format_datetime(datetime_):
            datetime_ = datetime_ or iso_utc()
            return datetime.strptime(datetime_, "%Y-%m-%dT%H:%M:%S.%f%z").strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )

        return {
            "_id": _object.get("Id"),
            "_timestamp": _format_datetime(datetime_=_object.get("LastModifiedDate")),
            "url": f"{self.base_url}/{_object.get('Id')}",
        } | _object

    def map_to_citymood(self, case):
        """Mappe un Case Salesforce vers le format attendu par le webhook
        CityMood (api/routers/webhook.py - EntryRequest).

        Format de sortie :
            {
                "source_type": "salesforce",
                "source_id": "<Case.Id>",
                "sender_email": "",
                "subject": "<Case.Subject>",
                "content": "<Case.Description>"
            }
        """
        return {
            "source_type": "salesforce",
            "source_id": case.get("Id", ""),
            "sender_email": "",
            "subject": case.get("Subject") or "",
            "content": case.get("Description") or "",
        }


class SalesforceDataSource(BaseDataSource):
    """Salesforce"""

    name = "Salesforce"
    service_type = "salesforce"
    advanced_rules_enabled = True
    dls_enabled = True
    incremental_sync_enabled = True

    def __init__(self, configuration):
        super().__init__(configuration=configuration)
        # CityMood : creds Issy depuis le .env (priorité sur la config ES).
        _SFDC_ENV_TO_CONFIG = {
            "SFDC_DOMAIN": "domain",
            "SFDC_CLIENT_ID": "client_id",
            "SFDC_CLIENT_SECRET": "client_secret",
        }
        for env_key, cfg_key in _SFDC_ENV_TO_CONFIG.items():
            if (val := os.environ.get(env_key)):
                configuration.get_field(cfg_key).value = val

        # case_fields est une liste : on splitte la chaîne du .env avant d'assigner.
        if (val := os.environ.get("CASE_FIELDS")):
            configuration.get_field("case_fields").value = [
                s.strip() for s in val.split(",") if s.strip()
            ]

        base_url = (
            SALESFORCE_EMULATOR_HOST
            if (RUNNING_FTEST and SALESFORCE_EMULATOR_HOST)
            else BASE_URL.replace("<domain>", configuration["domain"])
        )
        self.base_url_ = base_url
        self.salesforce_client = SalesforceClient(
            configuration=configuration, base_url=base_url
        )
        self.doc_mapper = SalesforceDocMapper(base_url)
        self.permissions = {}

        # CityMood : URLs et secrets pour la chaine anonymizer -> webhook.
        # Lus depuis les variables d'environnement du conteneur ingestion.
        self._anonymizer_url = os.environ.get(
            "ANONYMIZER_URL", "http://anonymizer-api:8000"
        )
        self._anonymizer_api_key = os.environ.get("ANONYMIZER_API_KEY", "")
        self._citymood_ingest_url = os.environ.get("CITYMOOD_INGEST_URL", "")
        self._citymood_tenant_id = os.environ.get("CITYMOOD_TENANT_ID", "")
        self._webhook_secret = os.environ.get("WEBHOOK_SECRET", "")
        self._http_session = None  # cree au premier appel (lazy)
        self._cleaning_pipeline = CleaningPipeline(
            [
                EncodingFixer(),
                ReplyChainStripper(),
                FooterStripper(),
                UrlStripper(),
                SignatureStripper(),
                PolitenessStripper(),
            ]
        )

    def _set_internal_logger(self):
        self.salesforce_client.set_logger(self._logger)

    @classmethod
    def get_default_configuration(cls):
        return {
            "domain": {
                "label": "Domain",
                "order": 1,
                "tooltip": "The domain for your Salesforce instance. If your Salesforce URL is 'foo.my.salesforce.com', the domain would be 'foo'.",
                "type": "str",
            },
            "client_id": {
                "label": "Client ID",
                "order": 2,
                "sensitive": True,
                "tooltip": "The client id for your OAuth2-enabled connected app. Also called 'consumer key'",
                "type": "str",
            },
            "client_secret": {
                "label": "Client Secret",
                "order": 3,
                "sensitive": True,
                "tooltip": "The client secret for your OAuth2-enabled connected app. Also called 'consumer secret'",
                "type": "str",
            },
            "standard_objects_to_sync": {
                "display": "textarea",
                "label": "Standard Objects to Sync",
                "order": 4,
                "tooltip": "The list of Salesforce Standard Objects to sync. Remove any from list to exclude from sync.",
                "type": "list",
                "value": ", ".join(STANDARD_SOBJECTS),
                "required": False,
            },
            "sync_custom_objects": {
                "display": "toggle",
                "label": "Sync Custom Objects",
                "order": 5,
                "tooltip": "Whether or not to sync custom objects",
                "type": "bool",
                "value": False,
            },
            "custom_objects_to_sync": {
                "display": "textarea",
                "label": "Custom Objects to Sync",
                "order": 6,
                "tooltip": "List of custom objects to sync. Use '*' to sync all custom objects. ",
                "type": "list",
                "depends_on": [{"field": "sync_custom_objects", "value": True}],
            },
            "case_fields": {
                "display": "textarea",
                "label": "Case fields to retrieve (CityMood)",
                "order": 7,
                "tooltip": (
                    "Liste des API names SFDC à récupérer sur l'objet Case. "
                    "À adapter par tenant (Issy, Airbus, Montans...). "
                    "Champs minimaux : contenu textuel, date. "
                    "Champs optionnels : lieu, catégorie, statut. "
                    "Exemple : Subject, Description, Status, Quartier__c, Theme__c"
                ),
                "type": "list",
                "value": "Subject, Description, CaseNumber, Status",
                "required": False,
            },
            "use_text_extraction_service": {
                "display": "toggle",
                "label": "Use text extraction service",
                "order": 7,
                "tooltip": "Requires a separate deployment of the Elastic Text Extraction Service. Requires that pipeline settings disable text extraction.",
                "type": "bool",
                "ui_restrictions": ["advanced"],
                "value": False,
            },
            "use_document_level_security": {
                "display": "toggle",
                "label": "Enable document level security",
                "order": 8,
                "tooltip": "Document level security ensures identities and permissions set in Salesforce are maintained in Elasticsearch. This enables you to restrict and personalize read-access users and groups have to documents in this index. Access control syncs ensure this metadata is kept up to date in your Elasticsearch documents.",
                "type": "bool",
                "value": False,
            },
        }

    def _dls_enabled(self):
        """Check if document level security is enabled. This method checks whether document level security (DLS) is enabled based on the provided configuration.

        Returns:
            bool: True if document level security is enabled, False otherwise.
        """
        if self._features is None:
            return False

        if not self._features.document_level_security_enabled():
            return False

        return self.configuration["use_document_level_security"]

    def _decorate_with_access_control(self, document, access_control):
        if self._dls_enabled():
            document[ACCESS_CONTROL] = list(
                set(document.get(ACCESS_CONTROL, []) + access_control)
            )
        return document

    async def _user_access_control_doc(self, user):
        email = user.get("Email")
        username = user.get("Name")

        prefixed_email = _prefix_email(email)
        prefixed_username = _prefix_user(username)
        prefixed_user_id = _prefix_user_id(user.get("Id"))

        access_control = [prefixed_email, prefixed_username, prefixed_user_id]
        return {
            "_id": user.get("Id"),
            "identity": {
                "email": prefixed_email,
                "username": prefixed_username,
                "user_id": prefixed_user_id,
            },
            "created_at": user.get("CreatedDate", iso_utc()),
            "_timestamp": user.get("LastModifiedDate", iso_utc()),
        } | es_access_control_query(access_control)

    async def get_access_control(self):
        """Get access control documents for Salesforce users.

        This method fetches access control documents for Salesforce users when document level security (DLS)
        is enabled. It starts by checking if DLS is enabled, and if not, it logs a warning message and skips further processing.
        If DLS is enabled, the method fetches all users from the Salesforce API, filters out Salesforce users,
        and fetches additional information for each user using the _fetch_user method. After gathering the user information,
        it generates an access control document for each user using the user_access_control_doc method and yields the results.

        Yields:
            dict: An access control document for each Salesforce user.
        """
        if not self._dls_enabled():
            self._logger.debug("DLS is not enabled. Skipping")
            return

        self._logger.debug("Fetching Salesforce users")
        async for user in self.salesforce_client.get_salesforce_users():
            if user.get("UserType") in ["CloudIntegrationUser", "AutomatedProcess"]:
                continue
            user_doc = await self._user_access_control_doc(user=user)
            yield user_doc

    async def validate_config(self):
        await super().validate_config()
        await self._remote_validation()

    async def _remote_validation(self):
        await self.salesforce_client.ping()

        if self.salesforce_client.sync_custom_objects:
            if self.salesforce_client.custom_objects_to_sync == [WILDCARD]:
                self.salesforce_client.custom_objects_to_sync = (
                    await self.salesforce_client._custom_objects()
                )
                return
            custom_object_response = await self.salesforce_client._custom_objects()

            if any(
                obj not in custom_object_response
                for obj in self.salesforce_client.custom_objects_to_sync
            ):
                msg = f"Custom objects {[obj[:-3] for obj in self.salesforce_client.custom_objects_to_sync if obj not in custom_object_response]} are not available."
                raise ConfigurableFieldValueError(msg)

    async def close(self):
        await self.salesforce_client.close()

    async def ping(self):
        try:
            await self.salesforce_client.ping()
            self._logger.debug("Successfully connected to Salesforce.")
        except Exception as e:
            self._logger.exception(f"Error while connecting to Salesforce: {e}")
            raise

    def advanced_rules_validators(self):
        return [SalesforceAdvancedRulesValidator(self)]

    async def _get_advanced_sync_rules_result(self, rule):
        async for doc in self.salesforce_client.get_sync_rules_results(rule=rule):
            if sobject := doc.get("attributes", {}).get("type"):
                await self._fetch_users_with_read_access(sobject=sobject)
            yield doc

    async def _fetch_users_with_read_access(self, sobject):
        if not self._dls_enabled():
            self._logger.debug("DLS is not enabled. Skipping")
            return

        self._logger.debug(
            f"Fetching users who have Read access for Salesforce object: {sobject}"
        )

        if sobject in self.permissions:
            return

        user_list = set()
        access_control = set()
        async for assignee in self.salesforce_client.get_users_with_read_access(
            sobject=sobject
        ):
            user_list.add(assignee.get("AssigneeId"))
            access_control.add(_prefix_user_id(assignee.get("AssigneeId")))

        if user_list == set():
            return

        user_sub_list = [
            list(user_list)[i : i + 800] for i in range(0, len(user_list), 800)
        ]
        for _user_list in user_sub_list:
            async for user in self.salesforce_client.get_username_by_id(
                user_list=tuple(_user_list)
            ):
                access_control.add(_prefix_user(user.get("Name")))
                access_control.add(_prefix_email(user.get("Email")))

        self.permissions[sobject] = list(access_control)

    async def get_docs(self, filtering=None):
        # CityMood : on ne synchronise que l'objet Case (pilote Issy).
        # Pas de full sync multi-objets, pas de DLS, pas de pieces jointes.
        # Chaque Case est envoye a l'anonymizer puis au webhook CityMood.
        standard_objects_to_sync = self.salesforce_client.standard_objects_to_sync

        if "Case" not in standard_objects_to_sync:
            logger.info("Case not in objects to sync — nothing to do.")
            return

        logger.info("Fetching Salesforce Cases for CityMood ingestion")
        async for case in self.salesforce_client.get_cases():
            await self._send_to_anonymizer(case)

    def _get_http_session(self):
        """Cree (ou reutilise) une session aiohttp pour les appels
        anonymizer + webhook. Une seule session par instance pour eviter
        l'overhead de creation/fermeture a chaque Case."""
        if self._http_session is None or self._http_session.closed:
            self._http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._http_session

    async def _anonymize_batch(self, texts):
        """Anonymise une liste de textes via l'API batch de l'anonymiseur (Mehdi).

        POST {ANONYMIZER_URL}/api/v1/anonymize/batch  (header X-API-Key)
            requête : {"texts": [...]}
            réponse : {"results": [{"anonymized_text": ..., "status": ...}, ...]}

        Retourne la liste des textes anonymisés, OU None si l'appel échoue ou si
        un statut n'est pas 'ok'. **Fail-closed (RGPD)** : en cas de doute on ne
        renvoie rien → le Case ne sera PAS transmis (jamais de PII en clair).
        """
        session = self._get_http_session()
        try:
            async with session.post(
                f"{self._anonymizer_url}/api/v1/anonymize/batch",
                json={"texts": texts},
                headers={"X-API-Key": self._anonymizer_api_key},
            ) as resp:
                resp.raise_for_status()
                results = (await resp.json())["results"]
        except Exception as exc:
            logger.error("[Anonymizer] echec appel batch : %s", exc, exc_info=True)
            return None

        anonymized = []
        for res in results:
            if res["status"] != "ok":
                logger.warning(
                    "[Anonymizer] statut '%s' -> Case non transmis (RGPD)",
                    res["status"],
                )
                return None
            anonymized.append(res["anonymized_text"])
        return anonymized

    async def _send_to_anonymizer(self, case):
        """Pipeline complet pour un Case Salesforce :
        1. Mapping vers le format CityMood
        2. Anonymisation du subject + content (PII supprimees)
        3. POST vers le webhook CityMood (cloud OVH)
        """
        if not self._citymood_ingest_url or not self._citymood_tenant_id:
            logger.warning(
                "[CityMood] CITYMOOD_INGEST_URL ou CITYMOOD_TENANT_ID manquant — "
                "Case ignore."
            )
            return

        payload = self.doc_mapper.map_to_citymood(case)
        payload["subject"] = self._cleaning_pipeline.run(payload["subject"])
        payload["content"] = self._cleaning_pipeline.run(payload["content"])

        # Anonymisation en batch (subject + content en 1 seul appel).
        anonymized = await self._anonymize_batch(
            [payload["subject"], payload["content"]]
        )
        if anonymized is None:
            return  # RGPD : anonymisation échouée/refusée -> on n'envoie rien
        payload["subject"], payload["content"] = anonymized

        session = self._get_http_session()
        headers = {
            "X-Tenant-Id": self._citymood_tenant_id,
            "X-Webhook-Secret": self._webhook_secret,
        }

        try:
            async with session.post(
                self._citymood_ingest_url,
                json=payload,
                headers=headers,
            ) as resp:
                resp.raise_for_status()
                logger.info(
                    "[CityMood] Case %s forwarded (status %s)",
                    payload["source_id"],
                    resp.status,
                )
        except Exception as exc:
            logger.error(
                "[CityMood] Echec POST webhook pour %s: %s",
                payload["source_id"],
                exc,
                exc_info=True,
            )

    async def get_content(self, doc, content_version_id):
        file_size = doc["content_size"]
        filename = doc["title"]
        file_extension = self.get_file_extension(filename)
        if not self.can_file_be_downloaded(file_extension, filename, file_size):
            return

        return await self.download_and_extract_file(
            doc,
            filename,
            file_extension,
            partial(
                self.generic_chunked_download_func,
                partial(
                    self.salesforce_client._download,
                    content_version_id,
                ),
            ),
            return_doc_if_failed=True,  # we still ingest on download failure for Salesforce
        )

    def _parse_content_documents(self, record):
        content_docs = []
        content_links = record.get("ContentDocumentLinks", {}) or {}
        content_links = content_links.get("records", []) or []
        for content_link in content_links:
            content_doc = content_link.get("ContentDocument")
            if not content_doc:
                continue

            content_doc["linked_sobject_id"] = record.get("Id")
            content_docs.append(content_doc)

        return content_docs

    def _combine_duplicate_content_docs(self, content_docs):
        """Duplicate ContentDocuments may appear linked to multiple SObjects
        Here we ensure that we don't download any duplicates while retaining links"""
        grouped = {}

        for content_doc in content_docs:
            content_doc_id = content_doc["Id"]
            if content_doc_id in grouped:
                linked_id = content_doc["linked_sobject_id"]
                linked_ids = grouped[content_doc_id]["linked_ids"]
                if linked_id not in linked_ids:
                    linked_ids.append(linked_id)
            else:
                grouped[content_doc_id] = content_doc
                grouped[content_doc_id]["linked_ids"] = [
                    content_doc["linked_sobject_id"]
                ]
                # the id is now in the list of linked_ids so we can delete it
                del grouped[content_doc_id]["linked_sobject_id"]

        grouped_objects = list(grouped.values())
        return grouped_objects
