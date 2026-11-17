app_name = "factory_productivity"
app_title = "Factory Productivity"
app_publisher = "Onichan"
app_description = "Production plans and reports"
app_email = ""
app_license = "Proprietary"
required_apps = ["factory_management"]
add_to_apps_screen = [{
    "name": app_name,
    "title": "Productivity Entry",
    "logo": "/assets/factory_productivity/images/productivity.svg",
    "route": "/app/productivity-entry",
    "has_permission": "factory_productivity.access.can_open",
}]
before_install = "factory_productivity.install.before_install"
after_install = "factory_productivity.install.after_migrate"
after_migrate = "factory_productivity.install.after_migrate"

