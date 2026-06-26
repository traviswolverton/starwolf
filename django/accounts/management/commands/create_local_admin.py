from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = "Create or update a local admin user with a password (bypasses Cloudflare auth)"

    def add_arguments(self, parser):
        parser.add_argument("email", help="Email / username for the account")
        parser.add_argument("password", help="Password for local login")

    def handle(self, *args, **options):
        email = options["email"]
        password = options["password"]
        user, created = User.objects.get_or_create(
            email=email,
            defaults={"username": email, "role": User.ADMIN},
        )
        user.set_password(password)
        user.role = User.ADMIN
        user.save()
        verb = "Created" if created else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} local admin: {email}"))
