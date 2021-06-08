from django.urls import reverse
from rest_framework.serializers import IntegerField, SerializerMethodField
from rest_framework_gis import serializers as gis_serializers
from swapper import load_model

from openwisp_users.api.mixins import FilterSerializerByOrgManaged
from openwisp_utils.api.serializers import ValidatedModelSerializer

Device = load_model('config', 'Device')
Location = load_model('geo', 'Location')
DeviceLocation = load_model('geo', 'DeviceLocation')
FloorPlan = load_model('geo', 'FloorPlan')


class LocationSerializer(gis_serializers.GeoFeatureModelSerializer):
    class Meta:
        model = Location
        geo_field = 'geometry'
        fields = ('name', 'geometry')
        read_only_fields = ('name',)


class LocationDeviceSerializer(ValidatedModelSerializer):
    admin_edit_url = SerializerMethodField('get_admin_edit_url')

    def get_admin_edit_url(self, obj):
        return self.context['request'].build_absolute_uri(
            reverse(f'admin:{obj._meta.app_label}_device_change', args=(obj.id,))
        )

    class Meta:
        model = Device
        fields = '__all__'


class GeoJsonLocationSerializer(gis_serializers.GeoFeatureModelSerializer):
    device_count = IntegerField()

    class Meta:
        model = Location
        geo_field = 'geometry'
        fields = '__all__'


class BaseSerializer(FilterSerializerByOrgManaged, ValidatedModelSerializer):
    pass


class FloorPlanSerializer(BaseSerializer):
    class Meta:
        model = FloorPlan
        fields = (
            'id',
            'floor',
            'image',
            'location',
            'created',
            'modified',
        )
        read_only_fields = ('created', 'modified')

    def validate(self, data):
        if data.get('location'):
            data['organization'] = data.get('location').organization
        instance = self.instance or self.Meta.model(**data)
        instance.full_clean()
        return data


class LocationModelSerializer(BaseSerializer):
    class Meta:
        model = Location
        fields = (
            'id',
            'organization',
            'name',
            'type',
            'is_mobile',
            'address',
            'geometry',
            'created',
            'modified',
        )
        read_only_fields = ('created', 'modified')


class DeviceLocationSerializer(BaseSerializer):
    class Meta:
        model = DeviceLocation
        fields = (
            'id',
            'indoor',
            'content_object',
            'location',
            'floorplan',
            'created',
            'modified',
        )
        read_only_fields = ('created', 'modified')
