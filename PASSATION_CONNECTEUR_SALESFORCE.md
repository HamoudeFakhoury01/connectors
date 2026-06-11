# Passation — Connecteur Salesforce CityMood

> Document de passation pour le développement du connecteur Salesforce.
> Dernière mise à jour : 11/06/2026 — warmup `/health` avant ingestion + TODO tests `get_docs` (voir §7)
> Précédente : 01/06/2026 — boîte ingestion Docker + creds via `.env` (voir §3c, §7, §10)
> Précédente : 08/05/2026 — Mohamed

---

## 1. Le contexte produit (à lire en premier)

**CityMood** = solution d'analyse des signaux faibles citoyens pour collectivités.

On déploie chez **Issy-les-Moulineaux** (1er client). Issy utilise **Salesforce** comme
outil de gestion des remontées citoyennes (objet `Case`). Notre job : récupérer ces
Cases, les anonymiser (retirer les données personnelles), et les envoyer à la
plateforme CityMood en cloud pour analyse.

### L'architecture cible (2 conteneurs Docker chez Issy)

```
┌──── Internet ──────────────────────┐
│   ┌──────────────┐                  │
│   │  SALESFORCE  │ (SaaS public)    │
│   │  instance Issy│                 │
│   └──────▲───────┘                  │
│          │ poll HTTPS 443           │
└──────────┼──────────────────────────┘
           │ OAuth + SOQL
┌──────────┼──────────────────────────┐
│  SI Issy │                          │
│   ┌──────┴──────┐    ┌──────────┐   │
│   │ INGESTION   │───▶│ANONYMIZER│   │
│   │ (ce repo)   │HTTP│          │   │
│   └─────────────┘8000└────┬─────┘   │
│                           │ POST    │
└───────────────────────────┼─────────┘
                            │ HTTPS 443
                            ▼
                   ┌──────────────────┐
                   │ CityMood (cloud) │
                   │ /webhook/entry   │
                   └──────────────────┘
```

- **Conteneur ingestion** = ce repo (le connecteur Salesforce). Poll SFDC, mappe, envoie.
- **Conteneur anonymizer** = `C:\Users\moham\Documents\Anonymization` (API qui retire les PII).
- **Backend CityMood** = `C:\Users\moham\Documents\Implem_criticite` (reçoit via webhook).

⚠️ **Décision d'archi en cours** : on hésite encore sur QUI envoie au webhook.
Aujourd'hui le code fait : ingestion → anonymizer (HTTP) → ingestion → webhook.
On veut basculer vers : ingestion → anonymizer → **anonymizer** envoie au webhook.
À trancher avec Mohamed avant de continuer.

---

## 2. D'où vient le code

On n'a PAS écrit le connecteur from scratch. On est parti du connecteur Salesforce
**open-source d'Elastic** (`elastic/connectors`), cloné dans :

```
C:\Users\moham\Documents\elastic-connectors
```

Le code Salesforce est dans :
```
app/connectors_service/connectors/sources/salesforce/
├── __init__.py        # exports
├── client.py          # ⭐ transport HTTP + OAuth + requêtes SOQL (1085 lignes)
├── constants.py       # endpoints, objets, champs
├── datasource.py      # ⭐ orchestrateur (config, poll, mapping)
└── validator.py       # validation règles avancées (pas utilisé)
```

### Pourquoi Elastic ?

Leur code gère déjà tout le pénible : OAuth, pagination Salesforce, retry sur 401,
gestion d'erreurs typées, query builder SOQL. On ne réinvente pas la roue.
On adapte juste la sortie (eux → Elasticsearch ; nous → webhook CityMood).

### Les 2 fichiers clés à comprendre

- **`client.py`** = "l'ouvrier". Sait COMMENT parler à Salesforce (HTTP, OAuth, SOQL).
- **`datasource.py`** = "le chef". Décide QUOI faire des données (mapper, envoyer).
  Le `datasource` UTILISE le `client`. Pas l'inverse.

---

## 3. Ce qu'on a déjà modifié

### a) `client.py` — champs Case configurables

**`__init__`** (vers ligne 94) : ajout de `self.case_fields`, lu depuis la config,
défaut = `["Subject", "Description", "CaseNumber", "Status"]`.

**`_cases_query()`** (vers ligne 783) : on a viré les 3 jointures lourdes
(EmailMessages, CaseComments, ContentDocuments) et on utilise `self.case_fields`.
La requête générée est maintenant minimaliste :
```sql
SELECT Id, CreatedDate, LastModifiedDate, Subject, Description, CaseNumber, Status
FROM Case
```

### b) `datasource.py` — mapping + envoi vers CityMood

**`SalesforceDocMapper.map_to_citymood(case)`** (vers ligne 88) : nouvelle méthode
qui transforme un Case SFDC vers le format du webhook CityMood (5 champs) :
```python
{
    "source_type": "salesforce",
    "source_id": case["Id"],
    "sender_email": "",
    "subject": case["Subject"],
    "content": case["Description"],
}
```

**`__init__`** (vers ligne 134) : ajout de 4 variables d'env lues depuis l'environnement :
`ANONYMIZER_URL`, `CITYMOOD_INGEST_URL`, `CITYMOOD_TENANT_ID`, `WEBHOOK_SECRET`.

**`get_docs()`** : simplifié drastiquement. On a viré toute la logique multi-objets
(Account, Lead, Opportunity, Campaign, Contact), le DLS, les pièces jointes.
Il ne reste que la boucle sur les Cases :
```python
async for case in self.salesforce_client.get_cases():
    await self._send_to_anonymizer(case)
```

**`_anonymize_text()`** + **`_send_to_anonymizer()`** : nouvelles méthodes qui
appellent l'anonymizer puis postent au webhook CityMood. Une session aiohttp
réutilisable est créée en lazy, fermée dans `close()`.
Logs paramétrés (`logger.info("... %s", x)`), pas de f-string.

### c) `datasource.py` — creds Salesforce d'Issy depuis le `.env` (01/06/2026)

**`__init__`** (tout en haut, AVANT la construction du client) : injection des
identifiants Salesforce depuis les variables d'environnement, en priorité sur la
config Elasticsearch. Objectif : remplir les creds d'Issy dans un simple `.env`
plutôt que dans Kibana.

```python
_SFDC_ENV_TO_CONFIG = {
    "SFDC_DOMAIN": "domain",
    "SFDC_CLIENT_ID": "client_id",
    "SFDC_CLIENT_SECRET": "client_secret",
}
for env_key, cfg_key in _SFDC_ENV_TO_CONFIG.items():
    if (val := os.environ.get(env_key)):
        configuration.get_field(cfg_key).value = val
# CASE_FIELDS : splitté en liste (champ de type list, pas str)
```

⚠️ Deux pièges : (1) l'injection doit rester **avant** la construction du client,
sinon le client reçoit l'ancienne valeur ; (2) `case_fields` est de type `list` →
il faut splitter la chaîne `.env` à la main (le setter `Field.value` ne reconvertit
pas). Si `.env` ET config ES sont vides → `validate_config()` plante bruyamment
(comportement voulu, sécurité/RGPD).

---

## 4. Le contrat du webhook CityMood (côté backend)

Le webhook qui reçoit nos données est dans :
```
C:\Users\moham\Documents\Implem_criticite\workflow-engine\api\routers\webhook.py
```

Endpoint : `POST /webhook/entry`

**Headers requis :**
- `X-Tenant-Id` : UUID du client (Issy). OBLIGATOIRE — permet le multi-tenant.
- `X-Webhook-Secret` : secret partagé. (Évoluera vers une vraie signature HMAC avant l'expé.)

**Body (Pydantic `EntryRequest`, exactement 5 champs) :**
```python
source_type: str = "email"   # on met "salesforce"
source_id: str = ""          # Case.Id
sender_email: str = ""       # vide pour Salesforce
subject: str = ""            # Case.Subject (anonymisé)
content: str = ""            # Case.Description (anonymisé)
```

⚠️ Ne PAS inventer d'autres champs. Le webhook n'en accepte que 5.

---

## 5. Le compte Salesforce de test (DÉJÀ CRÉÉ ET FONCTIONNEL)

On a créé une org **Salesforce Developer** gratuite pour tester.

- **Domaine** : `orgfarm-806a2e70b7-dev-ed.develop`
- **Connected App** créée : `CityMood Connector`
- **Auth** : OAuth 2.0 **Client Credentials Flow**
- **Scope** : `api` uniquement
- **Run As user** : configuré (obligatoire pour Client Credentials)

✅ On a validé que ça marche : on récupère bien 5 Cases de démo en SOQL.

### Tester l'auth (PowerShell)

```powershell
$clientId = "<CONSUMER_KEY>"
$clientSecret = "<CONSUMER_SECRET>"
$instance = "https://orgfarm-806a2e70b7-dev-ed.develop.my.salesforce.com"

$token = (Invoke-RestMethod -Uri "$instance/services/oauth2/token" -Method POST -Body @{
    grant_type = "client_credentials"
    client_id = $clientId
    client_secret = $clientSecret
}).access_token

$result = Invoke-RestMethod -Uri "$instance/services/data/v60.0/query?q=SELECT Id,Subject,Description FROM Case LIMIT 5" -Headers @{ Authorization = "Bearer $token" }
$result | ConvertTo-Json -Depth 5
```

Les Consumer Key / Secret sont à demander à Mohamed (non versionnés).

---

## 6. Configuration (variables d'environnement)

Le connecteur lit ces variables :

| Variable | Source | Description |
|----------|--------|-------------|
| `SFDC_DOMAIN` (→ `domain`) | Issy | Sous-domaine (ex. `ville-issy`) |
| `SFDC_CLIENT_ID` | Issy | Consumer Key de la Connected App |
| `SFDC_CLIENT_SECRET` | Issy | Consumer Secret |
| `CASE_FIELDS` | Issy | Champs métier à extraire |
| `ANONYMIZER_URL` | interne | URL du conteneur anonymizer (défaut `http://anonymizer-api:8000`) |
| `CITYMOOD_INGEST_URL` | CityMood | Endpoint webhook |
| `CITYMOOD_TENANT_ID` | CityMood | UUID tenant Issy |
| `WEBHOOK_SECRET` | CityMood | Secret webhook |

---

## 7. Ce qu'il reste à faire (TODO priorisé)

### Bloquant avant tout test bout-en-bout
1. **Trancher l'archi de sortie** (ingestion vs anonymizer qui poste au webhook) — avec Mohamed. _(toujours ouvert)_
2. ~~**Patcher les imports cassés**~~ → ✅ **RÉSOLU (01/06/2026)**. On garde le framework
   Elastic et on installe le SDK : le build Docker lance `make install-package` qui
   installe `libs/connectors_sdk` + l'app dans le venv. Les imports `connectors_sdk.*`
   se résolvent. Validé par `docker compose build ingestion` + import runtime (voir §10).
3. ~~**Persistance du bookmark**~~ → ✅ **RÉSOLU**. Avec le framework Elastic, l'état
   (curseur `LastModifiedDate`) est stocké dans l'index connecteur **Elasticsearch**,
   pas dans un volume local. Plus besoin du volume `./bookmark`.

### Important
4. **Gestion d'erreur webhook** : si le webhook CityMood est down, il faut une queue /
   retry / dead-letter. S'inspirer de `Implem_criticite/.../connectors/delivery.py`
   qui fait déjà ça côté backend (DLQ + retry).
5. **Polling configurable** : exposer `poll_interval_seconds` en variable d'env.
6. **Permission Set Salesforce** : le scope `api` donne accès à TOUT le CRM. La vraie
   restriction se fait via un Permission Set lecture seule sur `Case` côté Issy.
7. **Mettre à jour `tests/sources/test_salesforce.py`** _(dette héritée Mission 1)_.
   On a réécrit `get_docs()` : avant, elle `yield`-ait des docs (contrat Elastic →
   indexation ES) ; maintenant elle **pousse directement** chaque Case vers
   l'anonymiseur puis le webhook (aucun `yield`). Les ~8 tests `async for record, _ in
   source.get_docs()` testent donc l'**ancien** contrat → ils sont périmés/rouges sur
   notre fork. À refaire : tests du nouveau `get_docs` (mock anonymiseur + webhook) +
   un test du **warmup** `_wait_for_anonymizer` (cas healthy / cas fail-loud après
   timeout — penser à mocker l'appel `GET /api/v1/health`). À cadrer avec Mohamed
   (stratégie de test du connecteur). _Non bloquant : l'e2e de Mehdi couvre ce chemin._

### Plus tard
7. ~~Dockerfile + docker-compose pour les 2 conteneurs.~~ → ✅ **FAIT (01/06/2026)** :
   `deploy/citymood/` (voir §10). Reste à brancher la vraie image anonymizer.
8. Confirmer avec Issy les vrais noms de champs (`Quartier__c`, etc.) et si l'objet
   s'appelle bien `Case`.

---

## 8. Documents de référence

- **Annexe technique** (pour SPIE, l'infogérant Issy) : dernière version
  `Annexe_Technique_CityMood_v1.md`. Décrit le déploiement, les flux réseau, la config.
- **Registre de dette** : `Implem_criticite/workflow-engine/DEBT_REGISTER.md`
  (2 dettes liées à ce connecteur y sont documentées : BaseDataSource minimal, code Elastic repris en l'état).
- **Code de référence Elastic** : `Implem_criticite/references/elastic-connectors-salesforce/`
  (copie figée des 5 fichiers originaux, avant nos modifs).

---

## 9. Glossaire express

- **SOQL** : le SQL de Salesforce. `SELECT Id FROM Case`.
- **Client Credentials Flow** : OAuth sans utilisateur interactif, juste client_id + secret.
- **Connected App** : la déclaration côté Salesforce qui autorise notre accès API.
- **Case** : l'objet Salesforce standard = une réclamation / remontée citoyenne.
- **Bookmark** : l'horodatage du dernier Case traité, pour ne récupérer que les nouveaux.
- **PII** : données personnelles (nom, email, tel...) que l'anonymizer retire.
- **Tenant** : un client (Issy). Le backend est multi-tenant.
- **DLQ** : Dead Letter Queue, file des messages échoués à retraiter.

---

## 10. Déploiement Docker — boîte ingestion (fait le 01/06/2026)

Le conteneur ingestion est scaffoldé dans **`deploy/citymood/`** :

| Fichier | Rôle | Qui le remplit |
|---------|------|----------------|
| `docker-compose.yml` | Branche `ingestion` (ce repo) + `anonymizer-api`. | — (fini) |
| `.env.example` | Creds Issy (`SFDC_*`, `CASE_FIELDS`) + URLs CityMood. | Toi, quand Issy donne les creds |
| `config.yml.example` | Connexion Elasticsearch + enregistrement du connecteur. | Infra CityMood (host ES + `connector_id` Kibana) |

⚠️ **Sécurité** : les versions remplies `.env` et `config.yml` sont **gitignorées**
→ ne JAMAIS les committer. Seuls les `.example` sont versionnés.

### Lancer
```bash
cd deploy/citymood
cp .env.example .env              # puis remplir avec les infos d'Issy
cp config.yml.example config.yml  # puis remplir (host ES + connector_id Kibana)
docker compose up -d --build
```

### Tester (validé le 01/06/2026)
```bash
# 1. L'image build (installe le SDK + l'app) :
docker compose -f deploy/citymood/docker-compose.yml build ingestion

# 2. Les imports se résolvent à l'exécution :
docker run --rm citymood/ingestion:latest \
  /app/app/connectors_service/.venv/bin/python \
  -c "from connectors.sources.salesforce.datasource import SalesforceDataSource; print('OK')"

# 3. L'injection .env fonctionne (les 4 champs + split liste) : voir la commande
#    de test avec -e SFDC_DOMAIN=... dans l'historique de la session.
```

### Encore à faire pour un run réel (dépend de morceaux externes)
- creds réels d'Issy → dans `.env`,
- une instance Elasticsearch (CityMood) → dans `config.yml`,
- l'image `citymood/anonymizer` (repo de Mohamed) → branchée dans le compose
  (aujourd'hui `image: citymood/anonymizer:latest` = placeholder).

Travail livré sur la branche **`feat/docker-ingestion-citymood`** (fork
`HamoudeFakhoury01/connectors`).
