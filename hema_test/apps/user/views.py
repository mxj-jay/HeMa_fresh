from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
import re
from django.views.generic import View
from user.models import User, Address
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
from django.http import HttpResponse
from django.conf import settings
from celery_tasks.tasks import send_register_active_email
from django.contrib.auth import authenticate, login, logout
from utils.mixin import LonginRequiredMixin
from django.core.mail import send_mail
from django_redis import get_redis_connection
from goods.models import GoodsSKU
from order.models import OrderGoods,OrderInfo
from django.core.paginator import Paginator


class RegisterView(View):

    def get(self, request):

        return render(request, 'register.html')

    def post(self, request):

        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据校验 all
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'register.html', {'errmsg': '数据不完整'})

            # 是否同意协议
        if allow != 'on':
            return render(request, 'register.html', {'errmsg': '请同意协议'})

        # 邮箱验证
        if not re.match(r'^[a-z0-9][\w\.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'register.html', {'errmsg': '邮箱格式不正确'})
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            user = None

        if user:
            return render(request, 'register.html', {'errmsg': 'user is existing'})

        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm':user.id}
        token = serializer.dumps(info)
        token = token.decode()

        send_register_active_email.delay(email, username, token)

        return redirect(reverse('goods:index'))


class ActiveView(View):

    def get(self, request, token):

        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serializer.loads(token)
            user_id = info['confirm']
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            return redirect(reverse('user:login'))

        except SignatureExpired:
            return HttpResponse('Link expiration')


class LoginView(View):

    def get(self, request):

        if "username" in request.COOKIES:
            username = request.COOKIES.get("username")
            checked = "checked"

        else:
            username = ""
            checked = ""

        return render(request, 'login.html', {"username":username, "checked":checked})

    def post(self, request):

        username = request.POST.get("username")
        password = request.POST.get("pwd")

        if not all([username, password]):
            return render(request, "login.html", {"errmsg":"data not all"})

        user = authenticate(username=username, password=password)

        if user is not None:

            if user.is_active:

                login(request, user)

                next_url = request.GET.get("next", reverse("goods:index"))

                reponse = redirect(next_url)

                remember = request.POST.get("remember")
                if remember == "on":
                    reponse.set_cookie("username", username, max_age=1111)
                else:
                    reponse.delete_cookie("username")

                return reponse

            else:
                return render(request, "login.html", {"errmsg":"Please activate your account"})

        else:
            return render(request, "login.html", {"errmsg":"error in account"})


class LogoutView(View):

    def get(self, request):

        logout(request)

        return redirect(reverse("goods:index"))


class UserInfoView(LonginRequiredMixin, View):

    def get(self, request):

        user = request.user
        address = Address.objects.get_default_address(user)

        # from redis import StrictRedis
        # sr = StrictRedis(host="192.168.187.128", port=6379, db=9)

        con = get_redis_connection("default")

        history_key = "history_%d"%user.id
        sku_ids = con.lrange(history_key, 0, 4)

        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids)
        goods_li = []
        for id in sku_ids:
            goods = GoodsSKU.objects.get(id=id)
            goods_li.append(goods)

        context = {"page":"user",
                   "address":address,
                   "goods_li":goods_li}

        return render(request, "user_center_info.html", context)


class UserOrderView(LonginRequiredMixin, View):

    def get(self, request, page):

        user = request.user
        orders = OrderInfo.objects.filter(user=user)
        for order in orders:
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)

            for order_sku in order_skus:
                amount = order_sku.count * order_sku.price
                order_sku.amount = amount

            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            order.order_skus = order_skus

        paginator = Paginator(orders, 1)
        # page容错处理
        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages or page <= 0:
            page = 1

        order_page = paginator.page(page)

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

        context = {
            'order_page':order_page,
            'pages':pages,
            "page": "order"
        }

        return render(request, "user_center_order.html", context)


class AddressView(LonginRequiredMixin, View):

    def get(self, request):

        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except:
        #     # do not have default address
        #     address = None
        address = Address.objects.get_default_address(user)

        return render(request, "user_center_site.html", {"page":"address", "address":address})


    def post(self, request):

        receiver = request.POST.get("receiver")
        addr = request.POST.get("addr")
        zip_code = request.POST.get("zip_code")
        phone = request.POST.get("phone")

        if not all([receiver, addr, phone]):

            return render(request, "user_center_site.html", {"errmsg":"not all data"})

        if not re.match(r"^^([，；,;]*1\d{10}[，；,;]*)*$", phone):

            return render(request, "user_center_site.html", {"errmsg":"error in phone"})

        user = request.user
        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except:
        #     # do not have default address
        #     address = None
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        Address.objects.create(user=user, receiver=receiver,
                               addr=addr, zip_code=zip_code,
                               phone=phone, is_default=is_default)

        return redirect(reverse("user:address"))