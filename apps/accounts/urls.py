from django.urls import path

from . import views

urlpatterns = [
    path("tai-khoan/", views.account_list, name="accounts"),
    path("tai-khoan/them/", views.account_create, name="account-create"),
    path("tai-khoan/lich-su-dang-nhap/", views.login_history_list, name="login-history"),
    path("tai-khoan/ma-tran-quyen/", views.permission_matrix_view, name="permission-matrix"),
    path("tai-khoan/<uuid:user_id>/", views.account_detail, name="account-detail"),
    path("tai-khoan/<uuid:user_id>/sua/", views.account_update, name="account-update"),
    path("tai-khoan/<uuid:user_id>/khoa-mo/", views.account_toggle_lock, name="account-toggle-lock"),
    path("tai-khoan/<uuid:user_id>/dat-lai-mat-khau/", views.account_reset_password, name="account-reset-password"),
]

