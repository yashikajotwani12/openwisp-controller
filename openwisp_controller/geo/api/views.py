from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Count
from rest_framework import generics, pagination, status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.response import Response
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
    LocationModelSerializer,
    LocationSerializer,
)

Device = load_model('config', 'Device')
Location = load_model('geo', 'Location')
DeviceLocation = load_model('geo', 'DeviceLocation')
FloorPlan = load_model('geo', 'FloorPlan')


class DevicePermission(BasePermission):
    def has_object_permission(self, request, view, obj):
        return request.query_params.get('key') == obj.key


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


class DeviceLocationView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = LocationSerializer
    permission_classes = (DevicePermission,)
    queryset = Device.objects.select_related(
        'devicelocation', 'devicelocation__location'
    )

    def get_devicelocation(self):
        return super().get_object().devicelocation

    def get_location(self, device):
        try:
            return device.devicelocation.location
        except ObjectDoesNotExist:
            return None

    def get_object(self, *args, **kwargs):
        device = super().get_object()
        location = self.get_location(device)
        if location:
            return location
        # if no location present, automatically create it
        return self.create_location(device)

    def create_location(self, device):
        location = Location(
            name=device.name,
            type='outdoor',
            organization=device.organization,
            is_mobile=True,
        )
        location.full_clean()
        location.save()
        dl = DeviceLocation(content_object=device, location=location)
        dl.full_clean()
        dl.save()
        return location

    def destroy(self, request, *args, **kwargs):
        instance = self.get_devicelocation()
        self.perform_destroy(instance)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
    queryset = FloorPlan.objects.order_by('-created')
    pagination_class = ListViewPagination


class FloorPlanDetailView(
    ProtectedAPIMixin, generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = FloorPlanSerializer
    queryset = FloorPlan.objects.all()


class LocationListCreateView(ProtectedAPIMixin, generics.ListCreateAPIView):
    serializer_class = LocationModelSerializer
    queryset = Location.objects.order_by('-created')
    pagination_class = ListViewPagination


class LocationDetailView(
    ProtectedAPIMixin, generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = LocationModelSerializer
    queryset = Location.objects.all()


class DeviceLocationListCreateView(ProtectedAPIMixin, generics.ListCreateAPIView):
    serializer_class = DeviceLocationSerializer
    queryset = DeviceLocation.objects.order_by('-created')
    organization_field = 'location__organization'
    pagination_class = ListViewPagination


class DeviceLocationDetailView(
    ProtectedAPIMixin, generics.RetrieveUpdateDestroyAPIView,
):
    serializer_class = DeviceLocationSerializer
    queryset = DeviceLocation.objects.all()
    organization_field = 'location__organization'


device_location = DeviceLocationView.as_view()
geojson = GeoJsonLocationList.as_view()
location_device_list = LocationDeviceList.as_view()
list_floorplan = FloorPlanListCreateView.as_view()
detail_floorplan = FloorPlanDetailView.as_view()
list_location = LocationListCreateView.as_view()
detail_location = LocationDetailView.as_view()
device_location_list = DeviceLocationListCreateView.as_view()
device_location_detail = DeviceLocationDetailView.as_view()
