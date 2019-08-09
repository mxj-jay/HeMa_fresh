from django.contrib import admin
from goods.models import GoodsType,IndexPromotionBanner,IndexGoodsBanner,IndexTypeGoodsBanner, GoodsSKU, Goods, GoodsImage
from django.core.cache import cache


class BaseModelAdmin(admin.ModelAdmin):

    def save_model(self, request, obj, form, change):
        """新增或者更新的时候数据的调用"""
        super().save_model(request, obj, form, change)

        #发出celery任务　worker重新生成首页的静态页面
        #为什么要使用celery异步实现静态页面

        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        #清除首页的缓存的数据
        cache.delete("index_page_data")


    def delete_model(self, request, obj):
        """删除表中的数据时候调用"""
        super().delete_model(request, obj)

        from celery_tasks.tasks import generate_static_index_html
        generate_static_index_html.delay()

        # 清除首页的缓存的数据
        cache.delete("index_page_data")


class IndexPromotionBannerAdmin(BaseModelAdmin):
    pass


class GoodsTypeAdmin(BaseModelAdmin):
    pass


class IndexGoodsBannerAdmin(BaseModelAdmin):
    pass


class IndexTypeGoodsBannerAdmin(BaseModelAdmin):
    pass

admin.site.register(GoodsType,GoodsTypeAdmin)
admin.site.register(IndexPromotionBanner,IndexPromotionBannerAdmin)
admin.site.register(IndexGoodsBanner,IndexGoodsBannerAdmin)
admin.site.register(IndexTypeGoodsBanner,IndexTypeGoodsBannerAdmin)
admin.site.register(GoodsSKU)
admin.site.register(Goods)
admin.site.register(GoodsImage)
