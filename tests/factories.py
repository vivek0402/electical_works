from django.contrib.auth.models import Group, User

PASSWORD = "test-pass-123"


def make_user(username, role=None, superuser=False):
    user = User.objects.create_user(username=username, password=PASSWORD, first_name=username.title())
    if superuser:
        user.is_staff = user.is_superuser = True
        user.save()
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user
