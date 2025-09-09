import pkg_resources

def list_licenses():
    print(f"{'Package':30} {'Version':10} {'License'}")
    print("-" * 60)
    
    for dist in pkg_resources.working_set:
        name = dist.project_name
        version = dist.version
        try:
            license = dist.get_metadata("METADATA").split("License: ")[1].splitlines()[0]
        except Exception:
            try:
                license = dist.get_metadata("PKG-INFO").split("License: ")[1].splitlines()[0]
            except Exception:
                license = "Unknown"
        
        print(f"{name:30} {version:10} {license}")

if __name__ == "__main__":
    list_licenses()
