import os
import subprocess
import sys
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Builds the KuberLens V1.0 MkDocs static documentation site into site/ for in-app serving."

    def add_arguments(self, parser):
        parser.add_argument(
            "--regenerate-markdown",
            action="store_true",
            help="Regenerate all Markdown documentation files from the page inventory generator script.",
        )

    def handle(self, *args, **options):
        base_dir = settings.BASE_DIR
        self.stdout.write(self.style.NOTICE("Starting KuberLens User Guide build pipeline..."))

        if options.get("regenerate_markdown"):
            gen_script = base_dir / "scripts" / "build_kuberlens_docs.py"
            if gen_script.exists():
                self.stdout.write("Regenerating Markdown documentation source files...")
                res = subprocess.run([sys.executable, str(gen_script)], cwd=str(base_dir))
                if res.returncode != 0:
                    raise CommandError(f"Failed to regenerate Markdown docs (exit code {res.returncode})")

        # Run mkdocs build
        env = os.environ.copy()
        env["NO_MKDOCS_2_WARNING"] = "1"

        mkdocs_bin = base_dir / ".venv" / "bin" / "mkdocs"
        cmd = [str(mkdocs_bin) if mkdocs_bin.exists() else "mkdocs", "build", "--clean", "--strict"]

        self.stdout.write(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, cwd=str(base_dir), env=env, capture_output=True, text=True)

        if result.returncode != 0:
            self.stderr.write(result.stderr)
            raise CommandError(f"MkDocs build failed with exit code {result.returncode}")

        site_dir = base_dir / "site"
        index_file = site_dir / "index.html"
        if not index_file.exists():
            raise CommandError(f"Build completed, but {index_file} was not found.")

        html_count = len(list(site_dir.rglob("*.html")))
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully compiled {html_count} HTML pages into {site_dir}!\n"
                "Documentation is ready to serve directly at /help/ on the KuberLens application server."
            )
        )
