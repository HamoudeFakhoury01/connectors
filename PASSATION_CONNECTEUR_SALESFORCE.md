# Passation — Connecteur Salesforce CityMood

> Document de passation pour le développement du connecteur Salesforce.
> Dernière mise à jour : 08/05/2026 — Mohamed

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
1. **Trancher l'archi de sortie** (ingestion vs anonymizer qui poste au webhook) — avec Mohamed.
2. **Patcher les imports cassés** : le code Elastic importe `connectors_sdk.logger`,
   `connectors.access_control`, `connectors.utils` (CancellableSleeps, retryable),
   `connectors_sdk.source.BaseDataSource`. Ces modules viennent du SDK Elastic.
   → Soit installer le SDK, soit remplacer ces imports (logging standard, etc.).
3. **Persistance du bookmark** : `LastModifiedDate` doit survivre au redémarrage du
   conteneur (volume Docker `./bookmark`). Sinon doublons ou Cases perdus.

### Important
4. **Gestion d'erreur webhook** : si le webhook CityMood est down, il faut une queue /
   retry / dead-letter. S'inspirer de `Implem_criticite/.../connectors/delivery.py`
   qui fait déjà ça côté backend (DLQ + retry).
5. **Polling configurable** : exposer `poll_interval_seconds` en variable d'env.
6. **Permission Set Salesforce** : le scope `api` donne accès à TOUT le CRM. La vraie
   restriction se fait via un Permission Set lecture seule sur `Case` côté Issy.

### Plus tard
7. Dockerfile + docker-compose pour les 2 conteneurs.
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
