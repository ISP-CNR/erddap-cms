set -e
VERSION=1.3

docker build --platform linux/amd64 --target no-multiauth --build-arg CMS_VERSION=$VERSION --tag example.org/erddap-cms-no-multiauth:$VERSION --no-cache .
docker tag example.org/erddap-cms-no-multiauth:$VERSION example.org/erddap-cms-no-multiauth:latest
docker push example.org/erddap-cms-no-multiauth:$VERSION
docker push example.org/erddap-cms-no-multiauth:latest