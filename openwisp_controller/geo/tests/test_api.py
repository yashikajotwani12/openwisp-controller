import json
import tempfile

from django.contrib.auth.models import Permission
from django.contrib.gis.geos import Point
from django.test import TestCase
from django.test.client import BOUNDARY, MULTIPART_CONTENT, encode_multipart
from django.urls import reverse
from PIL import Image
from swapper import load_model

from openwisp_controller.config.tests.utils import CreateConfigTemplateMixin
from openwisp_controller.geo.tests.test_admin import FloorPlan
from openwisp_controller.tests.utils import TestAdminMixin
from openwisp_users.tests.utils import TestOrganizationMixin
from openwisp_utils.tests import AssertNumQueriesSubTestMixin, capture_any_output

from .utils import TestGeoMixin

Device = load_model('config', 'Device')
Location = load_model('geo', 'Location')
DeviceLocation = load_model('geo', 'DeviceLocation')
OrganizationUser = load_model('openwisp_users', 'OrganizationUser')


class TestApi(AssertNumQueriesSubTestMixin, TestGeoMixin, TestCase):
    url_name = 'geo_api:device_location'
    object_location_model = DeviceLocation
    location_model = Location
    object_model = Device

    def test_permission_404(self):
        url = reverse(self.url_name, args=[self.object_model().pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 404)

    def test_permission_403(self):
        dl = self._create_object_location()
        url = reverse(self.url_name, args=[dl.device.pk])
        r = self.client.get(url)
        self.assertEqual(r.status_code, 403)

    def test_method_not_allowed(self):
        device = self._create_object()
        url = reverse(self.url_name, args=[device.pk])
        r = self.client.post(url, {'key': device.key})
        self.assertEqual(r.status_code, 405)

    def test_get_existing_location(self):
        self.assertEqual(self.location_model.objects.count(), 0)
        dl = self._create_object_location()
        url = reverse(self.url_name, args=[dl.device.pk])
        self.assertEqual(self.location_model.objects.count(), 1)
        r = self.client.get(url, {'key': dl.device.key})
        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(
            r.json(),
            {
                'location': {
                    'type': 'Feature',
                    'geometry': json.loads(dl.location.geometry.geojson),
                    'properties': {
                        'type': 'outdoor',
                        'is_mobile': False,
                        'name': 'test-location',
                        'address': 'Via del Corso, Roma, Italia',
                    },
                },
                'floorplan': None,
                'indoor': None,
            },
        )
        self.assertEqual(self.location_model.objects.count(), 1)

    def test_get_create_location(self):
        self.assertEqual(self.location_model.objects.count(), 0)
        device = self._create_object()
        url = reverse(self.url_name, args=[device.pk])
        r = self.client.get(url, {'key': device.key})
        self.assertEqual(r.status_code, 200)
        self.assertDictEqual(
            r.json(),
            {
                'location': {
                    'type': 'Feature',
                    'geometry': None,
                    'properties': {
                        'type': 'outdoor',
                        'is_mobile': True,
                        'name': 'test-remove-mobile',
                        'address': '',
                    },
                },
                'floorplan': None,
                'indoor': '',
            },
        )
        self.assertEqual(self.location_model.objects.count(), 1)

    def test_patch_update_coordinates(self):
        self.assertEqual(self.location_model.objects.count(), 0)
        dl = self._create_object_location()
        url = reverse(self.url_name, args=[dl.device.pk])
        url = '{0}?key={1}'.format(url, dl.device.key)
        self.assertEqual(self.location_model.objects.count(), 1)
        coords = json.loads(Point(2, 23).geojson)
        data = {
            'location': {
                'type': 'Feature',
                'geometry': coords,
                'properties': {
                    'type': 'outdoor',
                    'is_mobile': False,
                    'name': dl.location.name,
                    'address': dl.location.address,
                },
            }
        }
        with self.assertNumQueries(3):
            r = self.client.patch(url, data, content_type='application/json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            r.data['location']['geometry']['coordinates'], coords['coordinates']
        )
        self.assertEqual(self.location_model.objects.count(), 1)

    def test_delete_device_location(self):
        self.assertEqual(self.location_model.objects.count(), 0)
        dl = self._create_object_location()
        url = reverse(self.url_name, args=[dl.device.pk])
        self.assertEqual(self.location_model.objects.count(), 1)
        self.assertEqual(self.object_location_model.objects.count(), 1)
        url = '{0}?key={1}'.format(url, dl.device.key)
        with self.assertNumQueries(4):
            r = self.client.delete(url)
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.object_location_model.objects.count(), 0)


class TestMultitenantApi(
    TestOrganizationMixin, TestGeoMixin, TestCase, CreateConfigTemplateMixin
):
    object_location_model = DeviceLocation
    location_model = Location
    object_model = Device

    def setUp(self):
        super().setUp()
        # create 2 orgs
        self._create_org(name='org_b', slug='org_b')
        org_a = self._create_org(name='org_a', slug='org_a')
        # create an operator for org_a
        ou = OrganizationUser.objects.create(
            user=self._create_operator(), organization=org_a
        )
        ou.is_admin = True
        ou.save()
        # create a superuser
        self._create_admin(is_superuser=True)

    def _create_device_location(self, **kwargs):
        options = dict()
        options.update(kwargs)
        device_location = self.object_location_model(**options)
        device_location.full_clean()
        device_location.save()
        return device_location

    @capture_any_output()
    def test_location_device_list(self):
        url = 'geo_api:location_device_list'
        # create 2 devices and 2 device location for each org
        device_a = self._create_device(organization=self._get_org('org_a'))
        device_b = self._create_device(organization=self._get_org('org_b'))
        location_a = self._create_location(organization=self._get_org('org_a'))
        location_b = self._create_location(organization=self._get_org('org_b'))
        self._create_device_location(content_object=device_a, location=location_a)
        self._create_device_location(content_object=device_b, location=location_b)

        with self.subTest('Test location device list for org operator'):
            self.client.login(username='operator', password='tester')
            r = self.client.get(reverse(url, args=[location_a.id]))
            self.assertContains(r, str(device_a.id))
            r = self.client.get(reverse(url, args=[location_b.id]))
            self.assertEqual(r.status_code, 404)

        with self.subTest('Test location device list for org superuser'):
            self.client.login(username='admin', password='tester')
            r = self.client.get(reverse(url, args=[location_a.id]))
            self.assertContains(r, str(device_a.id))
            r = self.client.get(reverse(url, args=[location_b.id]))
            self.assertContains(r, str(device_b.id))

        with self.subTest('Test location device list for unauthenticated user'):
            self.client.logout()
            r = self.client.get(reverse(url, args=[location_a.id]))
            self.assertEqual(r.status_code, 403)

    @capture_any_output()
    def test_geojson_list(self):
        url = 'geo_api:location_geojson'
        # create 2 devices and 2 device location for each org
        device_a = self._create_device(organization=self._get_org('org_a'))
        device_b = self._create_device(organization=self._get_org('org_b'))
        location_a = self._create_location(organization=self._get_org('org_a'))
        location_b = self._create_location(organization=self._get_org('org_b'))
        self._create_device_location(content_object=device_a, location=location_a)
        self._create_device_location(content_object=device_b, location=location_b)

        with self.subTest('Test geojson list for org operator'):
            self.client.login(username='operator', password='tester')
            r = self.client.get(reverse(url))
            self.assertContains(r, str(location_a.pk))
            self.assertNotContains(r, str(location_b.pk))

        with self.subTest('Test geojson list for superuser'):
            self.client.login(username='admin', password='tester')
            r = self.client.get(reverse(url))
            self.assertContains(r, str(location_a.pk))
            self.assertContains(r, str(location_b.pk))

        with self.subTest('Test geojson list unauthenticated user'):
            self.client.logout()
            r = self.client.get(reverse(url))
            self.assertEqual(r.status_code, 403)


class TestGeoApi(
    AssertNumQueriesSubTestMixin,
    TestOrganizationMixin,
    TestGeoMixin,
    TestAdminMixin,
    TestCase,
    CreateConfigTemplateMixin,
):
    location_model = Location
    floorplan_model = FloorPlan
    object_location_model = DeviceLocation

    def setUp(self):
        super().setUp()
        self._login()

    def _create_device_location(self, **kwargs):
        options = dict()
        options.update(kwargs)
        device_location = self.object_location_model(**options)
        device_location.full_clean()
        device_location.save()
        return device_location

    def test_get_floorplan_list(self):
        path = reverse('geo_api:list_floorplan')
        with self.assertNumQueries(3):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_filter_floorplan_list(self):
        f1 = self._create_floorplan(floor=10)
        org1 = self._create_org(name='org1')
        l1 = self._create_location(type='indoor', organization=org1)
        f2 = self._create_floorplan(floor=13, location=l1)
        staff_user = self._get_operator()
        change_perm = Permission.objects.filter(codename='change_floorplan')
        staff_user.user_permissions.add(*change_perm)
        self._create_org_user(user=staff_user, organization=org1, is_admin=True)
        self.client.force_login(staff_user)
        path = reverse('geo_api:list_floorplan')
        with self.assertNumQueries(6):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertContains(response, f2.id)
        self.assertNotContains(response, f1.id)

    def test_post_floorplan_list(self):
        l1 = self._create_location(type='indoor')
        path = reverse('geo_api:list_floorplan')
        temporary_image = tempfile.NamedTemporaryFile(suffix='.jpg')
        image = Image.new('RGB', (100, 100))
        image.save(temporary_image.name)
        data = {'floor': 1, 'image': temporary_image, 'location': l1.pk}
        with self.assertNumQueries(10):
            response = self.client.post(path, data, format='multipart')
        self.assertEqual(response.status_code, 201)

    def test_get_floorplan_detail(self):
        f1 = self._create_floorplan()
        path = reverse('geo_api:detail_floorplan', args=[f1.pk])
        with self.assertNumQueries(3):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_put_floorplan_detail(self):
        f1 = self._create_floorplan()
        l1 = self._create_location()
        path = reverse('geo_api:detail_floorplan', args=[f1.pk])
        temporary_image = tempfile.NamedTemporaryFile(suffix='.jpg')
        image = Image.new('RGB', (100, 100))
        image.save(temporary_image.name)
        data = {'floor': 12, 'image': temporary_image, 'location': l1.pk}
        with self.assertNumQueries(12):
            response = self.client.put(
                path, encode_multipart(BOUNDARY, data), content_type=MULTIPART_CONTENT
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['floor'], 12)
        self.assertEqual(response.data['location'], l1.pk)

    def test_patch_floorplan_detail(self):
        f1 = self._create_floorplan()
        self.assertEqual(f1.floor, 1)
        path = reverse('geo_api:detail_floorplan', args=[f1.pk])
        data = {'floor': 12}
        with self.assertNumQueries(10):
            response = self.client.patch(path, data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['floor'], 12)

    def test_delete_floorplan_detail(self):
        f1 = self._create_floorplan()
        path = reverse('geo_api:detail_floorplan', args=[f1.pk])
        with self.assertNumQueries(7):
            response = self.client.delete(path)
        self.assertEqual(response.status_code, 204)

    def test_get_location_list(self):
        path = reverse('geo_api:list_location')
        with self.assertNumQueries(3):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_filter_location_list(self):
        l1 = self._create_location(name='location-1')
        org1 = self._create_org(name='org1')
        l2 = self._create_location(type='indoor', organization=org1)
        staff_user = self._get_operator()
        change_perm = Permission.objects.filter(codename='change_location')
        staff_user.user_permissions.add(*change_perm)
        self._create_org_user(user=staff_user, organization=org1, is_admin=True)
        self.client.force_login(staff_user)
        path = reverse('geo_api:list_location')
        with self.assertNumQueries(6):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertContains(response, l2.id)
        self.assertNotContains(response, l1.id)

    def test_post_location_list(self):
        path = reverse('geo_api:list_location')
        coords = json.loads(Point(2, 23).geojson)
        data = {
            'organization': self._get_org().pk,
            'name': 'test-location',
            'type': 'outdoor',
            'is_mobile': False,
            'address': 'Via del Corso, Roma, Italia',
            'geometry': coords,
        }
        with self.assertNumQueries(6):
            response = self.client.post(path, data, content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_get_location_detail(self):
        l1 = self._create_location()
        path = reverse('geo_api:detail_location', args=[l1.pk])
        with self.assertNumQueries(3):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200)

    def test_put_location_detail(self):
        l1 = self._create_location()
        path = reverse('geo_api:detail_location', args=[l1.pk])
        org1 = self._create_org(name='org1')
        coords = json.loads(Point(2, 23).geojson)
        data = {
            'organization': org1.pk,
            'name': 'change-test-location',
            'type': 'outdoor',
            'is_mobile': False,
            'address': 'Via del Corso, Roma, Italia',
            'geometry': coords,
        }
        with self.assertNumQueries(7):
            response = self.client.put(path, data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['organization'], org1.pk)
        self.assertEqual(response.data['name'], 'change-test-location')

    def test_patch_location_detail(self):
        l1 = self._create_location()
        self.assertEqual(l1.name, 'test-location')
        path = reverse('geo_api:detail_location', args=[l1.pk])
        data = {'name': 'change-test-location'}
        with self.assertNumQueries(6):
            response = self.client.patch(path, data, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'change-test-location')

    def test_delete_location_detail(self):
        l1 = self._create_location()
        path = reverse('geo_api:detail_location', args=[l1.pk])
        with self.assertNumQueries(8):
            response = self.client.delete(path)
        self.assertEqual(response.status_code, 204)
