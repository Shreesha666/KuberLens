from django.views.generic.base import TemplateResponseMixin


class HTMXResponseMixin(TemplateResponseMixin):
    """
    Renders partial template when requested via HTMX (`request.htmx == True`),
    otherwise renders the full base shell template for direct URLs and browser refreshes.
    """
    partial_template_name = None
    active_nav = ""

    def get_template_names(self):
        if getattr(self.request, "htmx", False):
            if not self.partial_template_name:
                raise ValueError(
                    f"partial_template_name must be defined on {self.__class__.__name__} when using HTMXResponseMixin"
                )
            return [self.partial_template_name]
        return [self.template_name]

    def get_context_data(self, **kwargs):
        if hasattr(super(), "get_context_data"):
            context = super().get_context_data(**kwargs)
        else:
            context = kwargs
        context["active_nav"] = self.active_nav
        context["is_htmx"] = getattr(self.request, "htmx", False)
        return context
