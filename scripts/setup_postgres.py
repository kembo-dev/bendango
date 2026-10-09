"""Initialise PostgreSQL local, puis connecte Django après validation du schéma.

À lancer avec .venv/bin/python ; sudo demande le mot de passe dans le terminal.
Les données SQLite restent sauvegardées, sans import automatique dans PostgreSQL.
"""

import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / '.venv' / 'postgres-local.json'
ENV_FILE = ROOT / '.env'


def admin(statement):
    result = subprocess.run(
        ['sudo', '-u', 'postgres', 'psql', '-X', '-v', 'ON_ERROR_STOP=1',
         '-d', 'postgres', '-At'],
        input=statement, text=True, stdout=subprocess.PIPE, cwd='/tmp',
        stderr=subprocess.PIPE,
    )
    if result.returncode:
        raise RuntimeError('Commande PostgreSQL administrateur refusée ou échouée ; aucune configuration Django activée.')
    return result.stdout.strip()


def main():
    if Path(sys.prefix).resolve() != (ROOT / '.venv').resolve():
        raise RuntimeError('Utiliser .venv/bin/python scripts/setup_postgres.py depuis le projet.')
    # Obtenir sudo dans un terminal, sans lire ni conserver le mot de passe sudo.
    subprocess.run(['sudo', '-v'], check=True)
    if STATE.exists():
        state = json.loads(STATE.read_text())
    else:
        if admin("SELECT rolname FROM pg_roles WHERE rolname='bendango';"):
            raise RuntimeError('Le rôle bendango existe déjà. Demander sa configuration avant de changer ses identifiants.')
        if admin("SELECT datname FROM pg_database WHERE datname='bendango';"):
            raise RuntimeError('La base bendango existe déjà. Aucune donnée ni propriétaire modifié.')
        state = {'password': secrets.token_urlsafe(36)}
        fd = os.open(STATE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            json.dump(state, handle)

    if not admin("SELECT rolname FROM pg_roles WHERE rolname='bendango';"):
        statement = sql.SQL('CREATE ROLE bendango LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD {};').format(
            sql.Literal(state['password'])
        ).as_string()
        admin(statement)
    if not admin("SELECT datname FROM pg_database WHERE datname='bendango';"):
        admin('CREATE DATABASE bendango OWNER bendango;')

    with psycopg.connect(dbname='bendango', user='bendango', password=state['password'],
                         host='127.0.0.1', port=5432, connect_timeout=5) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT current_database(), current_user;')
            if cursor.fetchone() != ('bendango', 'bendango'):
                raise RuntimeError('Connexion à une base ou un rôle inattendu.')

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / '.venv' / f'db-before-postgres-{stamp}.sqlite3'
    source = ROOT / 'db.sqlite3'
    if source.exists():
        with sqlite3.connect(f'file:{source}?mode=ro', uri=True) as current:
            with sqlite3.connect(backup) as target:
                current.backup(target)
        backup.chmod(0o600)

    postgres = {
        'DB_ENGINE': 'postgresql', 'POSTGRES_DB': 'bendango',
        'POSTGRES_USER': 'bendango', 'POSTGRES_PASSWORD': state['password'],
        'POSTGRES_HOST': '127.0.0.1', 'POSTGRES_PORT': '5432',
        'POSTGRES_CONN_MAX_AGE': '60', 'POSTGRES_CONNECT_TIMEOUT': '5',
    }
    environment = {**os.environ, **postgres}
    for arguments in [('migrate', '--noinput'), ('check',)]:
        subprocess.run([sys.executable, 'manage.py', *arguments],
                       cwd=ROOT, env=environment, check=True)

    previous = ENV_FILE.read_text() if ENV_FILE.exists() else ''
    if ENV_FILE.exists():
        saved_env = ROOT / '.venv' / f'env-before-postgres-{stamp}.backup'
        fd = os.open(saved_env, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(previous)
    lines = [line for line in previous.splitlines()
             if line.partition('=')[0].strip().removeprefix('export ') not in postgres]
    lines.extend(f'{key}={value}' for key, value in postgres.items())
    temporary = ROOT / '.venv' / 'env-postgres.pending'
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write('\n'.join(lines) + '\n')
    temporary.replace(ENV_FILE)
    print('Base bendango créée et connexion Django validée. Configuration .env activée.')
    print('SQLite est conservé et sauvegardé ; PostgreSQL ne reçoit pas ses anciennes données.')
    print('Redémarrer le serveur et les workers pour charger la nouvelle connexion.')


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, subprocess.CalledProcessError, psycopg.Error) as error:
        # Ne pas exposer des identifiants ou une commande SQL dans les erreurs.
        print(f'Initialisation interrompue ({type(error).__name__}).', file=sys.stderr)
        if isinstance(error, RuntimeError):
            print(str(error), file=sys.stderr)
        sys.exit(1)
