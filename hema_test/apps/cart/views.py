from django.shortcuts import render
from django.views.generic import View
from django.http import JsonResponse
from goods.models import GoodsSKU
from django_redis import get_redis_connection
from utils.mixin import LonginRequiredMixin
# Create your views here.
"""
    传递参数:
        如果涉及到数据的修改（增删改），采用post
        只涉及到数据的获取，采用get
"""

class CartAddView(View):

    def post(self, request):

        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res':0,'errmsg':'Please login!'})

        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 数据校验
        if not all([sku_id,count]):
            return JsonResponse({'res':1,'errmsg':'data is not all'})
        try:
            count = int(count)
        except Exception as e:
            return  JsonResponse({'res':2,'errmsg':'商品数目出错'})
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res':3,'errmsg':'商品DoesNotExist'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id

        cart_count = conn.hget(cart_key, sku_id)
        if cart_count:
            count += int(cart_count)

        # 校验商品库存
        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足!'})
        conn.hset(cart_key, sku_id, count)

        total_count = conn.hlen(cart_key)

        return JsonResponse({'res':5,'errmsg':'Insert success!','total_count':total_count})


class CartInfoView(LonginRequiredMixin, View):

    def get(self,request):

        user = request.user

        conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id
        cart_dict = conn.hgetall(cart_key)

        skus = []
        total_count = 0
        total_price = 0
        for sku_id,count in cart_dict.items():
            sku = GoodsSKU.objects.get(id=sku_id)
            amount = sku.price * int(count)
            sku.amount = amount
            sku.count = count
            skus.append(sku)

            total_count += int(count)
            total_price += amount

        context = {
            'total_count':total_count,
            'total_price':total_price,
            'skus':skus
        }

        return render(request, 'cart.html', context)


# 采用ajax-post请求修改cart页面的购物车数量: sku_id , count
# /cart/update
class CartUpdateView(View):

    def post(self, request):

        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        sku_id = request.POST.get('sku_id')
        count = request.POST.get('count')

        # 数据校验
        if not all([sku_id, count]):
            return JsonResponse({'res': 1, 'errmsg': 'data is not all'})
        try:
            count = int(count)
        except Exception as e:
            return JsonResponse({'res': 2, 'errmsg': '商品数目出错'})
        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': '商品DoesNotExist'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id

        if count > sku.stock:
            return JsonResponse({'res': 4, 'errmsg': '商品库存不足'})

        conn.hset(cart_key, sku_id, count)

        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        return JsonResponse({'res': 5, 'total_count': total_count, 'errmsg': 'Update Successed!'})


class CartDeleteView(View):

    def post(self, request):
        user = request.user
        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        sku_id = request.POST.get('sku_id')

        if not sku_id:
            return JsonResponse({'res': 1, 'errmsg': '无效的商品id'})

        try:
            sku = GoodsSKU.objects.get(id=sku_id)
        except GoodsSKU.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '商品DoesNotExist'})

        conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id

        conn.hdel(cart_key, sku_id)

        total_count = 0
        vals = conn.hvals(cart_key)
        for val in vals:
            total_count += int(val)

        return JsonResponse({'res': 3, 'total_count': total_count, 'message': 'Delete success!'})

