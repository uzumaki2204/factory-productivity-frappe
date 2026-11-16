app_name = "factory_productivity"
app_title = "Factory Productivity"
app_publisher = "Onichan"
app_description = "Production plans and reports"
app_email = ""
app_license = "Proprietary"
required_apps = ["factory_management"]
before_install = "factory_productivity.install.before_install"
after_install = "factory_productivity.install.after_migrate"
after_migrate = "factory_productivity.install.after_migrate"

