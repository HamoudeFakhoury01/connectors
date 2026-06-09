# CityMood — Ingestion & Nettoyage (passation)

> Point d'entrée pour qui reprend ce travail. Raconte tout depuis la création du
> conteneur ingestion jusqu'au module de nettoyage, avec les **décisions et leur
> pourquoi**. Dernière MAJ : 09/06/2026.

---

## 0. Vue d'ensemble

CityMood récupère les remontées citoyennes (chez Issy : Salesforce), les **nettoie**,
les **anonymise**, puis les envoie à la plateforme CityMood pour analyse (NLP /
BERTrend).

```
[SALESFORCE]  →  [CONTENEUR INGESTION]                 →  [ANONYMISEUR]  →  [CityMood cloud]
   (poll)          = ce repo                               (NER, séparé)     /webhook/entry
                   1. connecteur (poll + mapping)
                   2. NETTOYAGE  ← ce dossier
```

- **Conteneur ingestion** = ce repo (fork Elastic connectors + connecteur Salesforce).
- **Nettoyage** = `connectors/cleaning/` (ce dossier) — tourne DANS le conteneur ingestion.
- **Anonymiseur** = conteneur séparé (Mehdi), utilise du **NER**.

---

## 1. Mission 1 — Le conteneur ingestion (branche `feat/docker-ingestion-citymood`)

> ⚠️ Cette partie vit sur l'**autre** branche, pas sur `feat/cleaning-module`.

- Parti du connecteur **Salesforce open-source d'Elastic** ; on adapte la sortie
  (eux → Elasticsearch ; nous → anonymiseur puis webhook CityMood).
- **Creds via `.env`** (pas Kibana) : `SFDC_DOMAIN`, `SFDC_CLIENT_ID`,
  `SFDC_CLIENT_SECRET`, `CASE_FIELDS` + `ANONYMIZER_URL`, `CITYMOOD_INGEST_URL`,
  `CITYMOOD_TENANT_ID`, `WEBHOOK_SECRET`. Injectés en haut de
  `SalesforceDataSource.__init__` (priorité sur la config ES).
- **Docker** : `deploy/citymood/` (`docker-compose.yml`, `.env.example`,
  `config.yml.example`). Image buildée et validée (le SDK + l'app s'installent).
- Détails complets : voir `PASSATION_CONNECTEUR_SALESFORCE.md`.

---

## 2. Mission 2 — Le module de nettoyage (cette branche)

Spec d'origine : `SPEC_MODULE_NETTOYAGE.md` (Mohamed). **Attention : on a dévié de la
spec sur 2 points (talon, spaCy) — voir §4.**

### 2.1 Architecture

- **Contrat** (`base.py`) : tout cleaner expose `clean(text: str) -> str` (pur,
  déterministe). ABC → fail-loud si un cleaner est incomplet.
- **Pipeline** (`pipeline.py`) : détient une **liste ordonnée** de cleaners et les
  applique en chaîne. **L'ordre est injecté** → réordonner = changer la liste, zéro
  réécriture. Valide le type d'entrée (fail-loud centralisé).

### 2.2 Les cleaners

| Fichier | Classe | Rôle | Outil |
|---|---|---|---|
| `encoding.py` | `EncodingFixer` | répare le mojibake + normalise les espaces insécables (Outlook) | `ftfy` |
| `reply_chain.py` | `ReplyChainStripper` | coupe les chaînes de réponse FR (`De :`/`Envoyé :`/`Le … a écrit :`) | regex |
| `footer.py` | `FooterStripper` | coupe les footers de confidentialité (`*****`, « Le contenu de ce courriel… ») | regex |
| `url.py` | `UrlStripper` | retire les URLs (http/https/www) | regex |
| `signature.py` | `SignatureStripper` | retire la signature (`-- `, « Sent from my… ») | `email_reply_parser` + regex |
| `politeness.py` | `PolitenessStripper` | retire ouvertures/clôtures (« Bonjour », « Cordialement »…) | regex FR |
| `normalize.py` | `SpacyNormalizer` | ⏸️ **MIS DE CÔTÉ** — minuscules/ponctuation/stopwords | spaCy |

### 2.3 Ordre du pipeline (visé)

```
Encoding → ReplyChain → Footer → Url → Signature → Politesse
```
- **Encoding en 1er** : les autres ont besoin de caractères propres.
- **ReplyChain/Footer tôt** : couper la chaîne/footer retire d'un coup leurs URLs/sigs.
- **SpacyNormalizer EXCLU** du pipeline pré-anonymiseur (voir §4).

---

## 3. Comment tester

```bash
# Tests unitaires (depuis app/connectors_service) :
PYTHONPATH=. python -m pytest connectors/cleaning/tests/ -o asyncio_mode=strict
#  → 15 verts + 1 skip (normalize, car spaCy retiré). Le test signature tourne en local
#    (email_reply_parser est pur Python).

# Lint/format (config repo) :
ruff format connectors/cleaning/ ; ruff check connectors/cleaning/
```

Test manuel sur un échantillon Excel (colonnes `subject`/`body`) : charger avec pandas,
construire un `CleaningPipeline([...])` et appliquer `.run()` sur chaque body.

---

## 4. Décisions clés & POURQUOI (le plus important)

1. **talon → `email_reply_parser`** (SignatureStripper).
   La spec disait talon, mais talon dépend de `cchardet`, une extension C++ qui exige
   un **compilateur absent de l'image Wolfi** (dépôt Chainguard minimal, pas de
   gcc/g++). `email_reply_parser` est **pur Python, zéro dépendance**, s'installe
   partout, et a été **audité** (sécu OK, pas de ReDoS). On a ajouté une regex maison
   pour les sig auto (« Sent from my iPhone ») qui polluaient BERTrend.

2. **spaCy mis de côté** (SpacyNormalizer).
   (a) L'anonymiseur de Mehdi utilise du **NER** → il a besoin de la **casse et de la
   ponctuation** pour repérer les noms ; or spaCy les détruit → spaCy doit tourner
   **après** l'anonymisation, pas avant. (b) Mohamed l'a jugé trop problématique pour
   l'instant. Donc : retiré des dépendances (image plus légère), code dormant, test
   auto-skip. **Quand on le réactivera : garder les chiffres** (déjà fait dans le code).

3. **Normalisation des insécables** (EncodingFixer).
   Outlook/Word insèrent des espaces insécables (U+00A0). Les regex à espaces littéraux
   (politesse) les rataient (« Bien à vous » survivait). On les normalise une fois, tôt.

4. **URL / ReplyChain / Footer ajoutés après test réel.**
   La spec visait des messages citoyens simples. Le test sur 250 vrais emails
   (corporate/santé) a montré beaucoup de bruit non prévu → on a ajouté ces 3 cleaners.

5. **Pas de sur-ingénierie** : pas de registry, pas de YAML. Une liste d'instances.

---

## 5. Validation sur données réelles (250 emails)

Échantillon : `echantillonage_test.xlsx` (emails CPTS/Assurance Maladie). Données déjà
en **UTF-8 propre** (pas de mojibake ; les `�` n'étaient que l'affichage console).

| Bruit | Avant | Après (6 cleaners) |
|---|---|---|
| URLs | 105/250 | **0** |
| Chaînes de réponse | 51/250 | 7 |
| Footers confidentialité | 16/250 | 4 |
| Insécables | présents | **0** |
| Signatures corporate | 27/250 | 23 |
| Tags image/logo | 28/250 | 24 |

Longueur body moyenne : **3774 → 2189 car (−42%)**. 250/250 traités, aucun crash
(1 body vide intercepté par le fail-loud).

---

## 6. Limites connues / bruit résiduel

- **Signatures corporate** (23) : bloc nom/fonction/service sans délimiteur `--`,
  difficile à cibler sans faux positifs. ⚠️ Les **noms = PII → job de l'anonymiseur NER**,
  pas du nettoyage.
- **Tags image/logo** (24) : `[cid:image…]`, `[ASSURANCE_MALADIE_Logo…]`. Candidat
  `ImageTagStripper` si jugé utile.
- **7 chaînes de réponse** edge (en-têtes collés sur une ligne) et **4 footers**
  (formulations non couvertes / « confidentiel » légitime).
- **Idempotence et taux de sur-nettoyage** : pas mesurés exhaustivement.

---

## 7. TODO (ce qui reste)

0. ✅ **FAIT — Brancher le pipeline dans `datasource.py`** : dans `_send_to_anonymizer`,
   on nettoie `subject` + `content` (6 cleaners) **entre** `map_to_citymood` et
   `_anonymize_text`. Pipeline créé une fois dans `__init__`. (commit `e5e0ec1`)
1. **Confirmer le contrat de l'anonymiseur de Mehdi** : le code suppose
   `POST {ANONYMIZER_URL}/api/v1/anonymize {"text": …} → {"anonymized_text": …}`.
   À vérifier/ajuster dans `_anonymize_text` — nécessaire pour le run e2e (n'a PAS
   bloqué le branchement).
2. ⚠️ **Merge des 2 branches** : `__init__` de `SalesforceDataSource` est modifié à la
   fois ici (création du pipeline) ET sur `feat/docker-ingestion-citymood` (injection
   `.env`). → **petit conflit à résoudre** au merge dans `main` (garder les deux blocs).
3. **Décision Mohamed** : ajouter `ImageTagStripper` / améliorer signatures, ou bruit
   actuel suffisant ?
4. **Réactiver spaCy APRÈS l'anonymisation** quand l'archi de sortie sera fixée
   (rappel : l'anonymiseur NER a besoin de la casse/ponctuation → spaCy va APRÈS).
5. **Ouvrir la PR** de `feat/cleaning-module` (base = fork `HamoudeFakhoury01`, **pas**
   Elastic).

---

## 8. Pointeurs

- Spec d'origine : `SPEC_MODULE_NETTOYAGE.md`
- Passation connecteur/ingestion : `PASSATION_CONNECTEUR_SALESFORCE.md`
- Branches : `feat/docker-ingestion-citymood` (mission 1), `feat/cleaning-module` (mission 2).
