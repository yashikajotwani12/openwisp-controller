from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from django.http import Http404
from rest_framework import generics, pagination
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework_gis.pagination import GeoJsonPagination
from swapper import load_model

from openwisp_users.api.authentication import BearerAuthentication
from openwisp_users.api.mixins import FilterByOrganizationManaged, FilterByParentManaged
from openwisp_users.api.permissions import DjangoModelPermissions

from .serializers import (
    DeviceLocationSerializer,
    FloorPlanSerializer,
    GeoJsonLocationSerializer,
    LocationDeviceSerializer,
    LocationSerializer,
)

Device = load_model('config', 'Device')
Location = load_model('geo', 'Location')
DeviceLocation = load_model('geo', 'DeviceLocation')
FloorPlan = load_model('geo', 'FloorPlan')


class DevicePermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.query_params.get('key'):
            received_key = request.query_params.get('key')
            try:
                device_key = obj.key
            except AttributeError:
                device_key = obj.device.key
            return received_key == device_key
        else:
            return False


class ListViewPagination(pagination.PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ProtectedAPIMixin(FilterByOrganizationManaged):
    authentication_classes = [BearerAuthentication, SessionAuthentication]
    permission_classes = [
        IsAuthenticated,
        DjangoModelPermissions,
    ]


class DeviceLocationView(
    FilterByOrganizationManaged, generics.RetrieveUpdateDestroyAPIView
):
    serializer_class = DeviceLocationSerializer
    authentication_classes = [
        BearerAuthentication,
        SessionAuthentication,
    ]
    permission_classes = [IsAuthenticated, DjangoModelPermissions]
    queryset = Device.objects.select_related(
        'devicelocation', 'devicelocation__location'
    )

    def get_organization_queryset(self, qs):
        # Overriding this method because the class
        # `FilterByOrganizationManaged` tries to
        # filter object for non-authenticated users.
        if self.request.user.is_authenticated and not self.request.query_params.get(
            'key'
        ):
            return qs.filter(
                **{
                    self.organization_lookup: getattr(
                        self.request.user, self._user_attr
                    )
                }
            )
        return qs

    def get_permissions(self):
        if not self.request.user.is_authenticated:
            return [
                DevicePermission(),
            ]
        elif 'key=' in self.request.META.get('QUERY_STRING'):
            return [
                DevicePermission(),
            ]
        else:
            return [
                IsAuthenticated(),
                DjangoModelPermissions(),
            ]

    def get_devicelocation(self, device):
        try:
            return device.devicelocation
        except ObjectDoesNotExist:
            return None

    def get_object(self, *args, **kwargs):
        device = super().get_object()
        devicelocation = self.get_devicelocation(device)
        if devicelocation:
            return devicelocation
        else:
            if self.request.method in ('GET', 'PATCH', 'DELETE'):
                raise Http404
            if self.request.method == 'PUT':
                return self.create_devicelocation(device)

    def create_devicelocation(self, device):
        location = Location(
            name=device.name,
            type='outdoor',
            organization=device.organization,
            is_mobile=True,
        )
        location.full_clean()
        location.save()
        dl = DeviceLocation(content_object=device, location=location, indoor="")
        dl.full_clean()
        dl.save()
        return dl


class GeoJsonLocationListPagination(GeoJsonPagination):
    page_size = 1000


class GeoJsonLocationList(FilterByOrganizationManaged, generics.ListAPIView):
    queryset = Location.objects.filter(devicelocation__isnull=False).annotate(
        device_count=Count('devicelocation')
    )
    serializer_class = GeoJsonLocationSerializer
    pagination_class = GeoJsonLocationListPagination


class LocationDeviceList(FilterByParentManaged, generics.ListAPIView):
    serializer_class = LocationDeviceSerializer
    pagination_class = ListViewPagination
    queryset = Device.objects.none()

    def get_parent_queryset(self):
        qs = Location.objects.filter(pk=self.kwargs['pk'])
        return qs

    def get_queryset(self):
        super().get_queryset()
        qs = Device.objects.filter(devicelocation__location_id=self.kwargs['pk'])
        return qs


class FloorPlanListCreateView(ProtectedAPIMixin, generics.ListCreateAPIView):
    serializer_class = FloorPlanSerializer
    queryset = FloorPlan.objects.select_related().order_by('-created')
    pagination_class = ListViewPagination


class FloorPlanDetailView(
    ProtectedAPIMixin, generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = FloorPlanSerializer
    queryset = FloorPlan.objects.select_related()


class LocationListCreateView(ProtectedAPIMixin, generics.ListCreateAPIView):
    serializer_class = LocationSerializer
    queryset = Location.objects.order_by('-created')
    pagination_class = ListViewPagination


class LocationDetailView(
    ProtectedAPIMixin, generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = LocationSerializer
    queryset = Location.objects.all()


device_location = DeviceLocationView.as_view()
geojson = GeoJsonLocationList.as_view()
location_device_list = LocationDeviceList.as_view()
list_floorplan = FloorPlanListCreateView.as_view()
detail_floorplan = FloorPlanDetailView.as_view()
list_location = LocationListCreateView.as_view()
detail_location = LocationDetailView.as_view()
