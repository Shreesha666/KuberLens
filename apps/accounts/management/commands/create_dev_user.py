from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

class Command(BaseCommand):
    help = "Creates a default superuser for local development"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin", help="Admin username")
        parser.add_argument("--password", default="Admin@12345", help="Admin password")
        parser.add_argument("--email", default="admin@example.com", help="Admin email")

    def handle(self, *args, **options):
        username = options["username"]
        password = options["password"]
        email = options["email"]

        if User.objects.filter(username=username).exists():
            self.stdout.write(self.style.WARNING(f"User '{username}' already exists."))
            return

        User.objects.create_superuser(
            username=username,
            email=email,
            password=password,
            first_name="Lead",
            last_name="Architect",
            phone_number="+919876543210",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created development superuser '{username}' with password '{password}'"
            )
        )
