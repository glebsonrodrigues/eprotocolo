from __future__ import annotations

import gzip
import os
import subprocess
import shutil
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Faz backup do banco (MySQL/MariaDB) usando mysqldump e salva em .sql.gz"

    def add_arguments(self, parser):
        parser.add_argument(
            "--outdir",
            default=str(Path(getattr(settings, "BASE_DIR", Path.cwd())) / "backups"),
            help="Diretório de saída (default: BASE_DIR/backups)",
        )
        parser.add_argument(
            "--plain",
            action="store_true",
            help="Salva .sql sem gzip (default é .sql.gz)",
        )
        parser.add_argument(
            "--mysqldump",
            default="",
            help="Caminho completo do mysqldump (opcional). Ex.: C:\\Program Files\\MySQL\\...\\mysqldump.exe",
        )

    def _find_mysqldump(self, cli_value: str) -> str:
        """
        Procura o mysqldump nesta ordem:
        1) --mysqldump (argumento)
        2) settings.MYSQLDUMP_PATH (se você quiser colocar no settings)
        3) env MYSQLDUMP_PATH (ideal no .env)
        4) PATH (shutil.which)
        """
        candidates = []

        if cli_value:
            candidates.append(cli_value)

        # opcional: se quiser definir em settings.py
        settings_value = getattr(settings, "MYSQLDUMP_PATH", "")
        if settings_value:
            candidates.append(settings_value)

        env_value = os.getenv("MYSQLDUMP_PATH", "")
        if env_value:
            candidates.append(env_value)

        # valida candidatos
        for c in candidates:
            p = Path(c).expanduser()
            if p.is_file():
                return str(p)

        # tenta no PATH
        found = shutil.which("mysqldump")
        if found:
            return found

        raise CommandError(
            "mysqldump não encontrado.\n\n"
            "Soluções:\n"
            "1) Instale MySQL Client ou MariaDB Client.\n"
            "2) Adicione a pasta 'bin' ao PATH.\n"
            "3) OU defina no .env: MYSQLDUMP_PATH=C:\\caminho\\para\\mysqldump.exe\n"
        )

    def handle(self, *args, **opts):
        db = settings.DATABASES.get("default", {})
        engine = db.get("ENGINE", "")

        if "mysql" not in engine:
            raise CommandError(f"ENGINE não suportado por este comando: {engine}")

        name = db.get("NAME")
        user = db.get("USER")
        password = db.get("PASSWORD", "")
        host = db.get("HOST") or "localhost"
        port = str(db.get("PORT") or "3306")

        if not all([name, user]):
            raise CommandError("DATABASES['default'] precisa de NAME e USER.")

        mysqldump_bin = self._find_mysqldump(opts.get("mysqldump") or "")

        outdir = Path(opts["outdir"])
        outdir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        base = f"{name}_{ts}.sql"
        out_sql = outdir / base
        out_gz = outdir / (base + ".gz")

        # Usa env var para não expor senha no comando (melhor que --password=...)
        env = os.environ.copy()
        if password:
            env["MYSQL_PWD"] = password

        # --databases garante que o dump venha com CREATE DATABASE/USE
        # --set-gtid-purged=OFF evita erro em alguns cenários (especialmente replicação/GTID)
        cmd = [
            mysqldump_bin,
            "--single-transaction",
            "--routines",
            "--triggers",
            "--events",
            "--default-character-set=utf8mb4",
            "--databases",
            "--set-gtid-purged=OFF",
            "-h", host,
            "-P", port,
            "-u", user,
            name,
        ]

        self.stdout.write(self.style.NOTICE(f"Gerando backup de '{name}'..."))
        self.stdout.write(self.style.NOTICE(f"Usando mysqldump: {mysqldump_bin}"))

        try:
            if opts["plain"]:
                with out_sql.open("wb") as f:
                    p = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, env=env)
                if p.returncode != 0:
                    raise CommandError(p.stderr.decode(errors="ignore") or "Falha no mysqldump.")
                self.stdout.write(self.style.SUCCESS(f"Backup criado: {out_sql}"))
            else:
                with gzip.open(out_gz, "wb") as gz:
                    p = subprocess.run(cmd, stdout=gz, stderr=subprocess.PIPE, env=env)
                if p.returncode != 0:
                    raise CommandError(p.stderr.decode(errors="ignore") or "Falha no mysqldump.")
                self.stdout.write(self.style.SUCCESS(f"Backup criado: {out_gz}"))
        finally:
            env.pop("MYSQL_PWD", None)
