from django.conf.urls import include, url
from django.contrib import admin
from cart.views import CartAddView, CartInfoView, CartUpdateView, CartDeleteView

urlpatterns = [

    url(r'^add$', CartAddView.as_view(), name='add'),
    url(r'^$', CartInfoView.as_view(), name='show'),  # 显示购物车页
    url(r'^update$', CartUpdateView.as_view(), name='update'),
    url(r'^delete$', CartDeleteView.as_view(), name='delete'),
]
