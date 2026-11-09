set -e
VERSION=6.2.2

docker build --platform linux/amd64 --target prod --build-arg CMS_VERSION=$VERSION --tag example.org/isp-erddap-cms:$VERSION .
docker tag example.org/isp-erddap-cms:$VERSION example.org/isp-erddap-cms:latest
docker push example.org/isp-erddap-cms:$VERSION
docker push example.org/isp-erddap-cms:latest