from django.urls import path

from . import views as api_views

app_name = 'openwisp_controller'


def get_api_urls(api_views):
    """
    returns:: all the API urls of the config app
    """
    return [
        path(
            'api/v1/controller/device/<uuid:id>/command/',
            api_views.command_list_create_view,
            name='device_command_list',
        ),
        path(
            'api/v1/controller/device/<uuid:id>/command/<uuid:command_id>/',
            api_views.command_details_view,
            name='device_command_details',
        ),
    ]


urlpatterns = get_api_urls(api_views)
