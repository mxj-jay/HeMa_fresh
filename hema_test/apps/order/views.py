from django.shortcuts import render, redirect
from django.views.generic import View
from django.core.urlresolvers import reverse
from goods.models import GoodsSKU
from user.models import Address
from order.models import OrderInfo, OrderGoods
from django_redis import get_redis_connection
from utils.mixin import LonginRequiredMixin
from django.http import JsonResponse
from datetime import datetime
from django.db import transaction
from alipay import AliPay
from utils.mixin import LonginRequiredMixin
from django.conf import settings
import os
# Create your views here.


# /order/place
class OrderPlaceView(LonginRequiredMixin, View):

    def post(self,request):

        user = request.user
        sku_ids = request.POST.getlist('sku_ids')

        if not sku_ids:

            return redirect(reverse('cart:show'))

        conn = get_redis_connection('default')
        cart_key = 'cart_%d'%user.id

        skus = []
        total_count = 0
        total_price = 0
        for sku_id in sku_ids:

            sku = GoodsSKU.objects.get(id=sku_id)
            count = conn.hget(cart_key, sku_id)
            amount = sku.price * int(count)
            # 动态增加属性
            sku.count = count
            sku.amount = amount

            skus.append(sku)
            total_count += int(count)
            total_price += amount

        transit_price = 10
        total_pay = total_price + transit_price

        addrs = Address.objects.filter(user=user)
        sku_ids = ','.join(sku_ids)

        context = {
            'skus':skus,
            'total_count':total_count,
            'total_price':total_price,
            'transit_price':transit_price,
            'total_pay':total_pay,
            'addrs':addrs,
            'sku_ids':sku_ids,
        }

        return render(request, 'place_order.html', context)


# 悲观锁 -- select * from df_goods_sku where id=17 for update;
class OrderCommitView1(View):
    """包含数据库的操作和事务操作"""
    # django -- 使用数据库事务方法
    @transaction.atomic
    def post(self, request):

        user = request.user

        if not user.is_authenticated:

            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        print(pay_method)
        sku_ids = request.POST.get('sku_ids')

        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': 'Data is not all!'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': 'Pay method error!'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': 'Address DoesNotExist!'})

        # todo: 设置事务保存点
        save_id = transaction.savepoint()

        try:
            # todo: 订单核心业务 '''order_id | total_count | total_price | transit_price |'''
            order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
            transit_price = 10
            total_count = 0
            total_price = 0

            order = OrderInfo.objects.create(order_id=order_id, user=user,
                                     addr=addr, pay_method=pay_method,
                                     total_count=total_count, total_price=total_price,
                                     transit_price=transit_price)

            # todo: 用户订单中有几个商品就需要加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d'%user.id
            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                try:
                    """sql:
                         ---悲观锁
                         select * from df_goods_sku where id=17 for update;
                    """
                    sku = GoodsSKU.objects.select_for_update.get(id=sku_id)
                except:
                    # todo: 商品不存在，事务回滚
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 3, 'errmsg': 'Goods DoesNotExist!'})

                # 从redis中获取用户所购买的商品内容
                count = conn.hget(cart_key, sku_id)

                OrderGoods.objects.create(order=order, sku=sku,
                                          count=count, price=sku.price)

                # todo: 判断商品的库存
                if int(count) > sku.stock:
                    # todo: 商品不存在，事务回滚
                    transaction.savepoint_rollback(save_id)
                    return JsonResponse({'res': 6, 'errmsg': 'Goods stock is null!'})

                # todo:更新商品的库存和销量
                sku.stock -= int(count)
                sku.sales += int(count)
                sku.save()

                amount = sku.price * int(count)
                total_count += int(count)
                total_price += amount

            # todo: 更新订单信息
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败!'})

        # todo:对事务进行提交
        transaction.savepoint_commit(save_id)
        # todo: 清除购物车
        conn.hdel(cart_key, *sku_ids)

        return JsonResponse({'res': 5, 'message': 'Create success!'})


# 乐观锁 -- update df_goods_sku set stock=0,sales=1 where id=17 and stock=1;
class OrderCommitView(View):
    """包含数据库的操作和事务操作"""
    # django -- 使用数据库事务方法
    @transaction.atomic
    def post(self, request):

        user = request.user

        if not user.is_authenticated:

            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        addr_id = request.POST.get('addr_id')
        pay_method = request.POST.get('pay_method')
        print(pay_method)
        sku_ids = request.POST.get('sku_ids')

        if not all([addr_id, pay_method, sku_ids]):
            return JsonResponse({'res': 1, 'errmsg': 'Data is not all!'})

        if pay_method not in OrderInfo.PAY_METHODS.keys():
            return JsonResponse({'res': 2, 'errmsg': 'Pay method error!'})

        try:
            addr = Address.objects.get(id=addr_id)
        except Address.DoesNotExist:
            return JsonResponse({'res': 3, 'errmsg': 'Address DoesNotExist!'})

        # todo: 设置事务保存点
        save_id = transaction.savepoint()

        try:
            # todo: 订单核心业务
            '''order_id | total_count | total_price | transit_price |'''
            order_id = datetime.now().strftime('%Y%m%d%H%M%S') + str(user.id)
            transit_price = 10
            total_count = 0
            total_price = 0

            order = OrderInfo.objects.create(order_id=order_id, user=user,
                                     addr=addr, pay_method=pay_method,
                                     total_count=total_count, total_price=total_price,
                                     transit_price=transit_price)

            # todo: 用户订单中有几个商品就需要加入几条记录
            conn = get_redis_connection('default')
            cart_key = 'cart_%d'%user.id
            sku_ids = sku_ids.split(',')
            for sku_id in sku_ids:
                for i in range(3):
                    try:
                        sku = GoodsSKU.objects.get(id=sku_id)
                    except:
                        # todo: 商品不存在，事务回滚
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 3, 'errmsg': 'Goods DoesNotExist!'})

                    # 从redis中获取用户所购买的商品内容
                    count = conn.hget(cart_key, sku_id)

                    OrderGoods.objects.create(order=order, sku=sku,
                                              count=count, price=sku.price)

                    # todo: 判断商品的库存
                    if int(count) > sku.stock:
                        # todo: 商品不存在，事务回滚
                        transaction.savepoint_rollback(save_id)
                        return JsonResponse({'res': 6, 'errmsg': 'Goods stock is null!'})

                    # todo:更新商品的库存和销量
                    origin_stock = sku.stock
                    new_stock = origin_stock - int(count)
                    new_sales = sku.sales + int(count)

                    """乐观锁 
                        -- update df_goods_sku set stock=0,sales=1 where id=17 and stock=1;
                    """
                    # 返回受影响的行数
                    res = GoodsSKU.objects.filter(id=sku_id, stock=origin_stock).update(stock=new_stock, sales=new_sales)
                    if res == 0:
                        if i == 2:
                            transaction.savepoint_rollback(save_id)
                            return JsonResponse({'res': 7, 'errmsg': '下单失败2!'})
                        continue

                    amount = sku.price * int(count)
                    total_count += int(count)
                    total_price += amount

                    break

            # todo: 更新订单信息
            order.total_count = total_count
            order.total_price = total_price
            order.save()
        except Exception as e:
            transaction.savepoint_rollback(save_id)
            return JsonResponse({'res': 7, 'errmsg': '下单失败!'})

        # todo:对事务进行提交
        transaction.savepoint_commit(save_id)
        # todo: 清除购物车
        conn.hdel(cart_key, *sku_ids)

        return JsonResponse({'res': 5, 'message': 'Create success!'})


class OrderPayView(View):

    def post(self, request):

        user = request.user

        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 0, 'errmsg': 'Order_id doesnot exit!'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务处理：使用python sdk调用支付宝的支付接口
        # alipay初始化
        app_private_key_string = open("apps/order/app_private_key.pem").read()
        alipay_public_key_string = open("apps/order/alipay_public_key.pem").read()

        alipay = AliPay(
            appid="2016100900646808",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False, 此处沙箱模拟True
        )

        # 调用支付接口
        # 电脑网站支付，需要跳转到https://openapi.alipaydev.com/gateway.do? + order_string
        total_pay = order.total_price + order.transit_price
        order_string = alipay.api_alipay_trade_page_pay(
            out_trade_no=order_id,  # 订单id
            total_amount=str(total_pay),  # 支付总金额
            subject='天天生鲜%s 用户' % order_id,
            return_url=None,
            notify_url=None  # 可选, 不填则使用默认notify url
        )

        pay_url = 'https://openapi.alipaydev.com/gateway.do?' + order_string
        return JsonResponse({'res': 3, 'pay_url': pay_url})


class CheckPayView(View):

    def post(self, request):
        user = request.user

        if not user.is_authenticated():
            return JsonResponse({'res': 0, 'errmsg': 'Please login!'})

        order_id = request.POST.get('order_id')

        if not order_id:
            return JsonResponse({'res': 0, 'errmsg': 'Order_id doesnot exit!'})

        try:
            order = OrderInfo.objects.get(order_id=order_id,
                                          user=user,
                                          pay_method=3,
                                          order_status=1)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'res': 2, 'errmsg': '订单错误'})

        # 业务处理：使用python sdk调用支付宝的支付接口
        # alipay初始化
        app_private_key_string = open("apps/order/app_private_key.pem").read()
        alipay_public_key_string = open("apps/order/alipay_public_key.pem").read()

        alipay = AliPay(
            appid="2016100900646808",  # 应用id
            app_notify_url=None,  # 默认回调url
            app_private_key_string=app_private_key_string,
            # 支付宝的公钥，验证支付宝回传消息使用，不是你自己的公钥,
            alipay_public_key_string=alipay_public_key_string,
            sign_type="RSA2",  # RSA 或者 RSA2
            debug=True  # 默认False, 此处沙箱模拟True
        )

        # 调用支付宝的交易查询接口
        while True:
            response = alipay.api_alipay_trade_query(order_id)

            # 返回字典
            # response = {
            # "trade_no": "2017032121001004070200176844",  # 支付宝交易号
            # "code": "10000",  # 接口调用成功
            # "invoice_amount": "20.00",
            # "open_id": "20880072506750308812798160715407",
            # "fund_bill_list": [
            #     {
            #         "amount": "20.00",
            #         "fund_channel": "ALIPAYACCOUNT"
            #     }
            # ],
            # "buyer_logon_id": "csq***@sandbox.com",
            # "send_pay_date": "2017-03-21 13:29:17",
            # "receipt_amount": "20.00",
            # "out_trade_no": "out_trade_no15",
            # "buyer_pay_amount": "20.00",
            # "buyer_user_id": "2088102169481075",
            # "msg": "Success",
            # "point_amount": "0.00",
            # "trade_status": "TRADE_SUCCESS",  # 支付结果
            # "total_amount": "20.00"
            # }
            code = response.get('code')

            if code == '10000' and response.get('trade_status') == 'TRADE_SUCCESS':
                # 支付成功
                trade_no = response.get('trade_no')
                # 更新订单状态
                order.trade_no = trade_no
                order.order_status = 4  # 待评价
                order.save()
                # 返回应答
                return JsonResponse({'res': 3, 'message': '支付成功'})

            elif code == '40004' or (code == '10000' and response.get('trade_status') == 'WAIT_BUYER_PAY'):
                # 等待买家付款 -- 循环
                import time
                time.sleep(5)
                continue
            else:
                # 支付出错
                return JsonResponse({'res': 4, 'errmsg': '支付失败'})


class OrderCommentView(LonginRequiredMixin, View):
    def get(self, request, order_id):
        """展示评论页"""
        user = request.user

        # 校验数据
        if not order_id:
            return redirect(reverse('user:order'))

        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 需要根据状态码获取状态
        order.status_name = OrderInfo.ORDER_STATUS[order.order_status]

        # 根据订单id查询对应商品，计算小计金额,不能使用get
        order_skus = OrderGoods.objects.filter(order_id=order_id)
        for order_sku in order_skus:
            amount = order_sku.count * order_sku.price
            order_sku.amount = amount
        # 增加实例属性
        order.order_skus = order_skus

        context = {
            'order': order,
        }
        return render(request, 'order_comment.html', context)

    def post(self, request, order_id):
        """处理评论内容"""
        # 判断是否登录
        user = request.user

        # 判断order_id是否为空
        if not order_id:
            return redirect(reverse('user:order'))

        # 根据order_id查询当前登录用户订单
        try:
            order = OrderInfo.objects.get(order_id=order_id, user=user)
        except OrderInfo.DoesNotExist:
            return redirect(reverse('user:order'))

        # 获取评论条数
        total_count = int(request.POST.get("total_count"))

        # 循环获取订单中商品的评论内容
        for i in range(1, total_count + 1):
            # 获取评论的商品的id
            sku_id = request.POST.get("sku_%d" % i)  # sku_1 sku_2
            # 获取评论的商品的内容
            content = request.POST.get('content_%d' % i, '')  # comment_1 comment_2

            try:
                order_goods = OrderGoods.objects.get(order=order, sku_id=sku_id)
            except OrderGoods.DoesNotExist:
                continue

            # 保存评论到订单商品表
            order_goods.comment = content
            order_goods.save()

        # 修改订单的状态为“已完成”
        order.order_status = 5  # 已完成
        order.save()
        # 1代表第一页的意思，不传会报错
        return redirect(reverse("user:order", kwargs={"page": 1}))

