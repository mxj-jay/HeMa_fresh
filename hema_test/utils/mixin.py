from django.contrib.auth.decorators import login_required

class LonginRequiredMixin(object):

    @classmethod
    def as_view(cls, **initkwargs):

        #调用父类的as_view的方法 View
        view = super(LonginRequiredMixin,cls).as_view(**initkwargs)

        #包装
        return login_required(view)