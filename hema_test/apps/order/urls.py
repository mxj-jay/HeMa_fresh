from django.conf.urls import include, url
from django.contrib import admin
from order.views import OrderPlaceView, OrderCommitView, OrderPayView, CheckPayView, OrderCommentView

urlpatterns = [

    url(r'^place$', OrderPlaceView.as_view(), name='place'),
    url(r'^commit$', OrderCommitView.as_view(), name='commit'),
    url(r'^pay$', OrderPayView.as_view(), name='pay'),
    url(r'^check$', CheckPayView.as_view(), name='check'),
    url(r'^comment/(?P<order_id>.+)$', OrderCommentView.as_view(), name='comment')
]
