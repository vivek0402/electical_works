import factory
from django.contrib.auth.models import Group, User

from apps.accounts.models import Profile

PASSWORD = "test-pass-123"


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    first_name = factory.Faker("first_name")
    password = factory.PostGenerationMethodCall("set_password", PASSWORD)

    @factory.post_generation
    def role(self, create, extracted, **kwargs):
        if create and extracted:
            self.groups.add(Group.objects.get(name=extracted))
        if create:
            Profile.objects.get_or_create(user=self)
            self.save()
