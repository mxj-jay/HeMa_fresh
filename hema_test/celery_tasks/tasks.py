from celery import Celery
from django.conf import settings
from django.core.mail import send_mail
from django_redis import get_redis_connection
from django.template import loader, RequestContext
import django
import time
#使用celery

""" 把这些内容加到任务处理者上面 
    使用 127.0.0.1：8000  和 192.168.187.128 访问是需要解除设置的
"""
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "test1.settings")
django.setup()

from goods.models import GoodsType, IndexPromotionBanner, IndexGoodsBanner, IndexTypeGoodsBanner


#创建一个celery的类的实例对象 默认写路径
app = Celery('celery_tasks.tasks', broker="redis://192.168.187.128:6379/8")

@app.task  #使用task方法进行装饰
def send_register_active_email(to_email,username,token):
    """发送邮件"""
    subject = 'welcome to tiantian shengxiam'
    html_message = "<h1>%s,welcome to tiantian shengxiam</h1>check this<br/><a href='http://127.0.0.1:8000/user/active/%s'>http://127.0.0.1:8000/user/active/%s</a>" % (
    username, token, token)
    sender = settings.EMAIL_FROM
    rec = [to_email]
    message = ''

    send_mail(subject, message, sender, rec, html_message=html_message)
    time.sleep(5)


@app.task
def generate_static_index_html():

    types = GoodsType.objects.all()

    goods_banners = IndexGoodsBanner.objects.all().order_by("index")

    promotion_banners = IndexPromotionBanner.objects.all().order_by("index")

    for type in types:
        # 获取type种类首页分类商品的图片展示信息
        image_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=1).order_by("index")

        # 获取type种类首页分类商品的文字展示信息
        title_banners = IndexTypeGoodsBanner.objects.filter(type=type, display_type=0).order_by("index")

        # 动态给type增加属性,分别报错首页分类商品的图片展示信息和文字的展示信息
        type.image_banners = image_banners
        type.title_banners = title_banners

        # 组织模板上下文
        context = {
            'types': types,
            'goods_banners': goods_banners,
            'promotion_banners': promotion_banners
        }

    temp = loader.get_template('static_index.html')

    # context = RequestContext(request, context)

    static_index_html = temp.render(context)

    save_path = os.path.join(settings.BASE_DIR, 'static/index.html')
    with open(save_path, 'w') as f:
        f.write(static_index_html)
