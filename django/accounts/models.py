from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    GUEST = "guest"
    USER = "user"
    ADMIN = "admin"
    ROLES = [(GUEST, "Guest"), (USER, "User"), (ADMIN, "Admin")]

    role = models.CharField(max_length=16, choices=ROLES, default=USER)

    def is_admin(self):
        return self.role == self.ADMIN

    def has_min_role(self, min_role: str) -> bool:
        order = [self.GUEST, self.USER, self.ADMIN]
        return order.index(self.role) >= order.index(min_role)

    class Meta:
        db_table = "starwolf_user"
