from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.views.generic import View
from goods.models import GoodsSKU,GoodsType,IndexGoodsBanner,IndexPromotionBanner,IndexTypeGoodsBanner
from django_redis import get_redis_connection
from order.models import OrderGoods
from django.core.paginator import Paginator
from django.core.cache import cache
# Create your views here.

#http://127.0.0.1:8000
class IndexView(View):
    """首页"""

    def get(self,request):
        """显示首页"""

        # todo: 尝试从缓存中获取数据
        context = cache.get('index_page_data')

        if context is None:

            print("设置缓存")

            #获取商品的种类信息
            types = GoodsType.objects.all()

            #获取首页轮播商品的信息
            goods_banners = IndexGoodsBanner.objects.all().order_by("index")

            #获取首页促销活动的信息
            promotion_banners = IndexPromotionBanner.objects.all().order_by("index")

            #获取首页分类商品的展示的信息
            for type in types:#GoodsType

                #获取type种类首页分类商品的图片展示信息
                image_banners = IndexTypeGoodsBanner.objects.filter(type = type,display_type = 1).order_by("index")

                #获取type种类首页分类商品的文字展示信息
                title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by("index")

                #动态给type增加属性,分别报错首页分类商品的图片展示信息和文字的展示信息
                type.image_banners = image_banners
                type.title_banners = title_banners

                # 组织模板上下文
                context = {
                    'types': types,
                    'goods_banners': goods_banners,
                    'promotion_banners': promotion_banners}

                #设置缓存
                cache.set('index_page_data',context,3600)


        #获取用户购物车商品的数目
        user = request.user
        cart_count = 0

        if user.is_authenticated():

            #用户已经登录
            conn = get_redis_connection("default")
            cart_key = 'cart_%d'%user.id
            cart_count = conn.hlen(cart_key)

        #组织模板的上下文
        context.update(cart_count = cart_count)

        #使用模板
        return render(request,'index.html',context)


class DetailView(View):

    def get(self, request, goods_id):

        try:
            sku = GoodsSKU.objects.get(id=goods_id)
        except GoodsSKU.DoesNotExist:
            return redirect(reverse('goods:index'))

        types = GoodsType.objects.all()
        sku_orders = OrderGoods.objects.filter(sku=sku).exclude(comment='')
        new_skus = GoodsSKU.objects.filter(type=sku.type).order_by("-id")[:2]

        same_spu_skus = GoodsSKU.objects.filter(goods=sku.goods).exclude(id=goods_id)

        user = request.user
        cart_count = 0

        if user.is_authenticated():
            # 用户已经登录
            conn = get_redis_connection("default")
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

            conn = get_redis_connection('default')
            history_key = 'history_%d'%user.id
            conn.lrem(history_key, 0, goods_id)
            conn.lpush(history_key, goods_id)
            conn.ltrim(history_key, 0, 4)


        context = {
            'sku':sku,
            'types':types,
            'sku_orders':sku_orders,
            'new_skus':new_skus,
            'cart_count':cart_count,
            'same_spu_skus':same_spu_skus
        }

        return render(request, 'detail.html', context)


class ListView(View):

    def get(self, request, type_id, page):

        try:
            type = GoodsType.objects.get(id=type_id)
        except GoodsType.DoesNotExist:
            return redirect(reverse('goods:index'))

        types = GoodsType.objects.all()
        # sort = default || sort = price || sort = hot
        sort = request.GET.get('sort')
        if sort == 'price':
            skus = GoodsSKU.objects.filter(type=type).order_by('price')
        elif sort == 'hot':
            skus = GoodsSKU.objects.filter(type=type).order_by('-sales')
        else:
            sort = 'default'
            skus = GoodsSKU.objects.filter(type=type).order_by('-id')

        paginator = Paginator(skus, 1)

        # page容错处理
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages or page <= 0:
            page = 1

        skus_page = paginator.page(page)
        # todo: 进行页码的控制，页面上最多显示5个页码
        # 1. 总数不足5页，显示全部
        # 2. 如当前页是前3页，显示1-5页
        # 3. 如当前页是后3页，显示后5页
        # 4. 其他情况，显示当前页的前2页，当前页，当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages - 4, num_pages + 1)
        else:
            pages = range(page - 2, page + 3)

        new_skus = GoodsSKU.objects.filter(type=type).order_by("-id")[:2]

        user = request.user
        cart_count = 0

        if user.is_authenticated():
            # 用户已经登录
            conn = get_redis_connection("default")
            cart_key = 'cart_%d' % user.id
            cart_count = conn.hlen(cart_key)

        context = {
            'type':type, 'types':types,
            'skus_page':skus_page,
            'new_skus':new_skus,
            'cart_count':cart_count,
            'sort':sort
        }


        return render(request, 'list.html', context)




