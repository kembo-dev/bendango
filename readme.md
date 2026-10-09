# Bendango

Bendango est un comparateur de prix Django avec collecte asynchrone, PostgreSQL, Redis, workers parallèles, SearchRun isolés, scoring de candidats, mémoire de santé des domaines et suivi temps réel des recherches.

---

## 1. Prérequis système

Environnement actuellement utilisé :

- Ubuntu / Linux
- Python via `pyenv`
- environnement virtuel : `bendango`
- projet : `/home/alexandre/Documents/bendango`
- PostgreSQL local
- Redis local

Installer les dépendances système :

```bash
sudo apt update
sudo apt install postgresql postgresql-contrib redis-server
```

Activer PostgreSQL et Redis au démarrage :

```bash
sudo systemctl enable --now postgresql
sudo systemctl enable --now redis-server
```

Vérifier Redis :

```bash
redis-cli ping
```

Résultat attendu :

```text
PONG
```

---

## 2. Environnement Python

Activer l'environnement :

```bash
pyenv activate bendango
```

Vérifier les exécutables utilisés :

```bash
which python
which pip
```

Dans l'installation actuelle, Python est attendu ici :

```text
/home/alexandre/.pyenv/versions/bendango/bin/python
```

Installer les dépendances Python :

```bash
pip install -r requirements.txt
```

Les dépendances principales incluent notamment :

- Django
- psycopg
- django-redis
- redis
- requests
- beautifulsoup4
- boto3
- gunicorn

---

## 3. PostgreSQL local

Nom de la base :

```text
bendango
```

Utilisateur recommandé :

```text
bendango
```

Créer l'utilisateur et la base :

```bash
sudo -u postgres psql
```

Puis dans PostgreSQL :

```sql
CREATE USER bendango WITH PASSWORD 'TON_MOT_DE_PASSE';
CREATE DATABASE bendango OWNER bendango;
GRANT ALL PRIVILEGES ON DATABASE bendango TO bendango;
\q
```

Tester la connexion :

```bash
psql -h 127.0.0.1 -U bendango -d bendango
```

---

## 4. Configuration `.env`

Créer ou compléter le fichier :

```text
/home/alexandre/Documents/bendango/.env
```

Exemple :

```env
# Django
DJANGO_DEBUG=True
DJANGO_SECRET_KEY=change-me
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

# PostgreSQL
DB_ENGINE=postgresql
POSTGRES_DB=bendango
POSTGRES_USER=bendango
POSTGRES_PASSWORD=TON_MOT_DE_PASSE
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_CONN_MAX_AGE=60
POSTGRES_CONNECT_TIMEOUT=5

# Redis
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_KEY_PREFIX=bendango
REDIS_CONNECT_TIMEOUT=2
REDIS_SOCKET_TIMEOUT=2
REDIS_DEFAULT_TIMEOUT=300

# LLM
LLM_PROVIDER=bedrock
LLM_MODEL=TON_MODELE
LLM_MODELS=TON_MODELE
AWS_REGION=us-east-1

# Workers / scraping
SCRAPE_MAX_WORKERS=4
SCRAPE_DOMAIN_LOCK_TIMEOUT=30
SCRAPE_DOMAIN_BUSY_DELAY=2
SCRAPE_JOB_MAX_ATTEMPTS=3
SCRAPE_JOB_RUNNING_TIMEOUT=300
SCRAPE_JOB_PRIORITY_WINDOW=40

# Couverture de marché
MARKET_COVERAGE_TARGET=3
SCRAPE_COVERAGE_WINDOW_MINUTES=30

# Santé des domaines
DOMAIN_HEALTH_WINDOW_HOURS=24
DOMAIN_HEALTH_SAMPLE_SIZE=12
DOMAIN_FETCH_CIRCUIT_FAILURES=2
DOMAIN_FETCH_CIRCUIT_MINUTES=10

# Collecte HTTP
COLLECTION_MAX_ATTEMPTS=3
COLLECTION_TIMEOUT=20
COLLECTION_CONNECT_TIMEOUT=4
COLLECTION_READ_TIMEOUT=8
COLLECTION_HTML_CACHE_TTL=300
COLLECTION_DOMAIN_MIN_INTERVAL=0.35

# Recherche
DEFAULT_SEARCH_COUNTRY=RDC
LOCAL_SEARCH_DOMAINS=drcmart.com,mobile-rdc.com
```

Ne jamais versionner les vrais mots de passe, clés AWS ou secrets Django.

---

## 5. Initialisation Django

Appliquer les migrations :

```bash
python manage.py migrate
```

Vérifier qu'aucune migration ne manque :

```bash
python manage.py makemigrations --check
```

Vérifier la configuration Django :

```bash
python manage.py check
```

Lancer tous les tests :

```bash
python manage.py test tracker --failfast
```

---

## 6. Lancement manuel en développement

### Terminal 1 — Django

```bash
pyenv activate bendango
cd ~/Documents/bendango
python manage.py runserver
```

Application :

```text
http://127.0.0.1:8000/
```

### Terminal 2 — workers

```bash
pyenv activate bendango
cd ~/Documents/bendango
python manage.py run_scrape_worker --workers 3
```

Exemple de sortie :

```text
Starting 3 Bendango scrape workers
job 100: success (...)
job 101: retry/fetch_failed (...)
run abcdef12 coverage reached: cancelled 14 queued job(s)
job 120: skipped/coverage_reached (...)
```

---

## 7. Fonctionnement des workers

Bendango utilise :

- 3 workers parallèles en usage normal ;
- PostgreSQL pour les jobs, résultats et SearchRun ;
- Redis pour le cache partagé et les verrous distribués ;
- 1 fetch simultané maximum par domaine ;
- priorité aux jobs `fresh` avant les retries ;
- early-stop lorsqu'un SearchRun atteint le nombre de marchands cible ;
- annulation coopérative des jobs devenus inutiles ;
- mémoire de santé des domaines ;
- ranking URL + titre + snippet avant fetch.

Lancement recommandé :

```bash
python manage.py run_scrape_worker --workers 3
```

---

## 8. SearchRun et progression temps réel

Chaque nouvelle recherche possède un UUID `SearchRun` distinct.

Exemple :

```text
run=24876133
query=Tecno Spark 40 8GB 256GB
```

Deux recherches identiques restent indépendantes.

La progression peut afficher :

```text
Sources découvertes : 28
Sources analysées    : 7
Offres trouvées      : 2
Marchands            : 2 / 3
```

Une fois la couverture atteinte :

```text
Recherche terminée
3 / 3 marchands
```

---

## 9. Monitoring de la queue

Résumé global :

```bash
python manage.py scrape_queue_status
```

Sur la dernière heure :

```bash
python manage.py scrape_queue_status --recent-hours 1
```

Pour une recherche :

```bash
python manage.py scrape_queue_status --query "hp victus"
```

JSON :

```bash
python manage.py scrape_queue_status --json
```

---

## 10. Architecture locale

```text
Navigateur
    |
    v
Gunicorn / Django
    |
    +-------------------+
    |                   |
    v                   v
PostgreSQL             Redis
SearchRun              cache
ScrapeJob              locks domaines
PriceListing           coordination
    ^
    |
Worker 1
Worker 2
Worker 3
```

---

## 11. Gunicorn

Gunicorn est utilisé pour le service web permanent.

Test manuel :

```bash
/home/alexandre/.pyenv/versions/bendango/bin/gunicorn \
  config.wsgi:application \
  --bind 127.0.0.1:8000 \
  --workers 3 \
  --timeout 60
```

Vérifier son chemin :

```bash
which gunicorn
ls -l /home/alexandre/.pyenv/versions/bendango/bin/gunicorn
```

---

## 12. Services systemd

Les fichiers sont présents dans :

```text
deploy/systemd/bendango-web.service
deploy/systemd/bendango-worker.service
```

Ils utilisent actuellement :

```text
WorkingDirectory=/home/alexandre/Documents/bendango
EnvironmentFile=/home/alexandre/Documents/bendango/.env
Python=/home/alexandre/.pyenv/versions/bendango/bin/python
Gunicorn=/home/alexandre/.pyenv/versions/bendango/bin/gunicorn
```

Si le projet ou le virtualenv change de chemin, modifier ces fichiers avant installation.

Installer les services :

```bash
sudo cp deploy/systemd/bendango-web.service /etc/systemd/system/
sudo cp deploy/systemd/bendango-worker.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable bendango-web
sudo systemctl enable bendango-worker
```

Démarrer :

```bash
sudo systemctl start bendango-web
sudo systemctl start bendango-worker
```

Ou activer immédiatement :

```bash
sudo systemctl enable --now bendango-web
sudo systemctl enable --now bendango-worker
```

Vérifier :

```bash
systemctl status bendango-web --no-pager
systemctl status bendango-worker --no-pager
```

Résultat attendu :

```text
Active: active (running)
```

---

## 13. Logs systemd

Logs web :

```bash
journalctl -u bendango-web -f
```

Logs workers :

```bash
journalctl -u bendango-worker -f
```

Dernières lignes :

```bash
journalctl -u bendango-web -n 100 --no-pager
journalctl -u bendango-worker -n 100 --no-pager
```

---

## 14. Redémarrage après mise à jour

Après un `git pull` / `git rebase` :

```bash
pyenv activate bendango
cd ~/Documents/bendango

pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test tracker --failfast

sudo systemctl restart bendango-web
sudo systemctl restart bendango-worker
```

Puis :

```bash
systemctl status bendango-web --no-pager
systemctl status bendango-worker --no-pager
```

---

## 15. Mise à jour Git recommandée

Récupérer les changements distants :

```bash
git fetch origin
git rebase origin/clean/bendango-v2
```

Si des modifications locales existent :

```bash
git status
git add .
git commit -m "local changes before rebase"
git fetch origin
git rebase origin/clean/bendango-v2
```

Ne pas utiliser `git reset --hard` si des changements locaux doivent être conservés.

---

## 16. Diagnostic `systemd` — erreur 203/EXEC

Une erreur :

```text
status=203/EXEC
```

signifie généralement que `ExecStart` pointe vers un exécutable absent ou non accessible.

Vérifier :

```bash
which python
which gunicorn
ls -l /home/alexandre/.pyenv/versions/bendango/bin/python
ls -l /home/alexandre/.pyenv/versions/bendango/bin/gunicorn
```

Puis remettre les fichiers systemd à jour :

```bash
sudo systemctl stop bendango-web bendango-worker

sudo cp deploy/systemd/bendango-web.service /etc/systemd/system/
sudo cp deploy/systemd/bendango-worker.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl reset-failed bendango-web bendango-worker
sudo systemctl start bendango-web bendango-worker
```

---

## 17. Commandes utiles PostgreSQL

État du service :

```bash
systemctl status postgresql --no-pager
```

Connexion :

```bash
psql -h 127.0.0.1 -U bendango -d bendango
```

Lister les bases depuis le compte postgres :

```bash
sudo -u postgres psql -c '\l'
```

---

## 18. Commandes utiles Redis

État :

```bash
systemctl status redis-server --no-pager
```

Ping :

```bash
redis-cli ping
```

Afficher quelques clés Bendango :

```bash
redis-cli --scan --pattern 'bendango*'
```

---

## 19. Dépannage rapide

### Django ne démarre pas

```bash
python manage.py check
python manage.py migrate
journalctl -u bendango-web -n 100 --no-pager
```

### Workers ne démarrent pas

```bash
/home/alexandre/.pyenv/versions/bendango/bin/python manage.py run_scrape_worker --workers 3
journalctl -u bendango-worker -n 100 --no-pager
```

### Redis indisponible

```bash
sudo systemctl restart redis-server
redis-cli ping
```

### PostgreSQL indisponible

```bash
sudo systemctl restart postgresql
psql -h 127.0.0.1 -U bendango -d bendango
```

### Vérifier l'ensemble du projet

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test tracker --failfast
python manage.py scrape_queue_status --recent-hours 1
```

---

## 20. Configuration de production

Pour une vraie mise en production Internet :

- passer `DJANGO_DEBUG=False` ;
- définir un `DJANGO_SECRET_KEY` fort ;
- configurer `DJANGO_ALLOWED_HOSTS` ;
- utiliser HTTPS ;
- placer Nginx ou un autre reverse proxy devant Gunicorn ;
- sauvegarder PostgreSQL ;
- protéger Redis du réseau public ;
- ne jamais exposer PostgreSQL directement sur Internet ;
- conserver les secrets uniquement dans `.env` ou un gestionnaire de secrets ;
- superviser `bendango-web`, `bendango-worker`, PostgreSQL et Redis.

Exemple production :

```env
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=bendango.example.com
DJANGO_SECRET_KEY=UN_SECRET_LONG_ET_ALEATOIRE
```

---

## 21. Workflow quotidien recommandé

Développement :

```bash
pyenv activate bendango
cd ~/Documents/bendango
python manage.py runserver
```

Workers manuels :

```bash
python manage.py run_scrape_worker --workers 3
```

Installation permanente :

```bash
sudo systemctl enable --now bendango-web bendango-worker
```

Monitoring :

```bash
journalctl -u bendango-worker -f
```

Tests avant push/déploiement :

```bash
python manage.py check
python manage.py makemigrations --check
python manage.py test tracker --failfast
```

sudo systemctl enable bendango-search-worker
sudo systemctl enable bendango-worker
sudo systemctl enable bendango-web

sudo systemctl start bendango-search-worker
sudo systemctl start bendango-worker
sudo systemctl start bendango-web

sudo systemctl stop bendango-search-worker
sudo systemctl stop bendango-worker
sudo systemctl stop bendango-web

sudo systemctl status bendango-search-worker
sudo systemctl status bendango-worker
sudo systemctl status bendango-web
## Styles Tailwind

L'interface utilise Tailwind CSS 4 et une base Django commune. Le CSS compilé
`tracker/static/tracker/css/app.css` est livré avec le projet ; Node n'est pas
nécessaire pour servir cette feuille existante.

Pour modifier le thème ou les classes (Node et pnpm 11 nécessaires) :

```bash
pnpm install --frozen-lockfile
pnpm run build:css
.venv/bin/python manage.py collectstatic --noinput
```

`pnpm run watch:css` surveille les changements pendant le développement.
Modifier `assets/css/app.css` et les templates, puis livrer la feuille générée.
Exécuter `collectstatic` avant les tests utilisant le stockage à manifeste Django.


## Choisir le LLM : local, API ou AWS

La configuration partagée est `config/llm.toml`. Le profil actif livré, `legacy`,
conserve `LLM_PROVIDER` et `LLM_MODEL` de votre installation. Les profils disponibles :

| Profil | Usage |
| --- | --- |
| `local` | Ollama local, modèle `gemma3:4b` à installer dans Ollama |
| `studio` | Serveur local compatible OpenAI, par exemple LM Studio |
| `api` | API compatible Chat Completions, avec clé |
| `aws` | Bedrock Converse et authentification AWS |
| `legacy` | Variables historiques de l'installation |

```bash
.venv/bin/python manage.py llm_config --list
.venv/bin/python manage.py llm_config --profile local --check
.venv/bin/python manage.py llm_config --use local
```

`--use` écrit la préférence dans `config/llm.local.toml`, ignoré par Git. Vous pouvez
éditer ce fichier pour personnaliser vos modèles sans modifier la configuration commune :

```toml
active_profile = "local"

[profiles.local]
model = "gemma3:4b"

[profiles.studio]
model = "nom-du-modele-charge-dans-votre-serveur"
```

Pour une API, renseigner dans `.env` les variables suivantes avec les valeurs de
votre fournisseur ; la clé reste privée :

```dotenv
LLM_API_KEY=votre-cle-privee
LLM_API_MODEL=nom-du-modele-compatible
LLM_API_BASE_URL=https://api.openai.com/v1
```

Redémarrer web et workers après modification de `.env`, puis :

```bash
.venv/bin/python manage.py llm_config --profile api --check
.venv/bin/python manage.py llm_config --use api
```

Le TOML est relu à chaque appel : modèle, URL, température, limite de sortie et
contexte peuvent être modifiés sans redémarrer. `LLM_PROFILE` impose un profil
par environnement et prend priorité sur la sélection du fichier. Les nouvelles
recherches gardent leur référence `profil::modèle` ; vider les anciennes files
sans préfixe avant une bascule. Un profil utilisé par des travaux en cours doit
rester disponible. Un secours distant exige une autorisation explicite dans `[policy]`.

`--check` ne fait aucun appel réseau : il valide la configuration et la présence
de la clé requise, sans tester les droits API ni la disponibilité du modèle.
Les profils `api` et `studio` contiennent des noms de modèles d'exemple à remplacer.
Le serveur local doit être déjà lancé. La compatibilité API exige les paramètres
Chat Completions employés (notamment `temperature` et `max_tokens`) ; choisir
`json_mode = "none"` si le serveur ne prend pas en charge `response_format`.
Les API distantes utilisent HTTPS ; HTTP est accepté sur localhost uniquement.

Références : [Ollama Chat](https://docs.ollama.com/api/chat),
[OpenAI Chat Completions](https://developers.openai.com/api/reference/resources/chat),
[Bedrock Converse](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html).


### Fonctionner sans modèle configuré

Le mode livré est `auto` : Bendango tente JSON-LD/métadonnées/HTML, puis le LLM
si un profil utilisable est configuré. Sans modèle ou clé, la recherche continue.
Les données invérifiables sont ignorées ; aucune valeur de prix n'est inventée.
Les résultats signalent les pages en échec et leur éventuelle couverture incomplète.

```toml
[policy]
mode = "auto"                 # auto, disabled ou required
fallback_profile = ""         # par exemple "local", pour un secours explicite
allow_paid_fallback = false
```

`disabled` interdit les appels LLM, même si un modèle est configuré. `required`
exige une configuration utilisable et arrête l'extraction complémentaire si tous
les adaptateurs autorisés échouent ; l'extraction locale réussie reste valable.
Les nouvelles tâches créées sans LLM restent sans LLM si un modèle est ajouté ensuite.
Un secours est essayé une seule fois ; un endpoint distant (y compris Bedrock)
exige `allow_paid_fallback = true`. Aucun fournisseur alternatif n'est choisi seul.

Diagnostic opérateur sans appel API : `manage.py llm_config --check` pour l'état
courant, ou `manage.py llm_config --profile api --check` pour vérifier strictement
un profil. Les logs précisent les options manquantes, sans publier les clés.
Un fichier absent autorise le mode auto ; un TOML malformé ou un mode inconnu doit
être corrigé et ne provoque aucun appel à un fournisseur.
