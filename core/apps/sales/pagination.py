from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class SalesBarcodeLookupPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "is_multiple": bool(getattr(self.request, "_is_multiple", False)),
                "products": {
                    "count": self.page.paginator.count,
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "results": data,
                },
            }
        )


class SalesHistoryPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


