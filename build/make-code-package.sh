#!/usr/bin/env bash

CODE=code

VERSION_NUMBER=0.0.1
BUILD=${BUILD_NUMBER:-0}

CONTAINER="build-deb-"$(echo $RANDOM % 100 + 1 | bc)

PACKAGE_PATH="/opt/${CODE}"
PACKAGE_ML=/python/packages

docker build --tag $CODE \
             --file build/Dockerfile.code .

docker run -t --name $CONTAINER \
    --volume $(pwd)/src:/src \
    --volume $(pwd)/build:/build \
    $CODE \
    bash -c "pip3 install --upgrade pip \
    && pip3 install --upgrade twine \
    && pip3 install --upgrade wheel \
    && pip3 install --upgrade setuptools \
    && cd src \
    && echo $VERSION_NUMBER-$BUILD > version.txt \
    && echo mymodel==$VERSION_NUMBER-$BUILD > requirements-ml.txt \
    && python3 setup.py bdist_wheel \
    && twine upload --repository-url https://******/repository/pypi-internal/ dist/*.whl -u user -p password \
    && cd .. \
    && python3 -m venv ${PACKAGE_PATH}/venv \
    && ${PACKAGE_PATH}/venv/bin/pip3 install --upgrade pip \
    && ${PACKAGE_PATH}/venv/bin/pip3 install --upgrade wheel \
    && ${PACKAGE_PATH}/venv/bin/pip3 install --upgrade setuptools \
    && ${PACKAGE_PATH}/venv/bin/pip3 install --index-url https://******/repository/pypi-all/simple \
                                        -r /src/requirements.txt\
    && ${PACKAGE_PATH}/venv/bin/pip3 install --no-deps --index-url https://******/repository/pypi-all/simple \
                                        -r /src/requirements-ml.txt\
    && ${PACKAGE_PATH}/venv/bin/pip3 install --index-url https://******/repository/pypi-all/simple \
                                        -r /src/requirements-local.txt\
    && rm -f ${PACKAGE_ML}/*\
    && ${PACKAGE_PATH}/venv/bin/pip3 download --no-deps --index-url https://******/repository/pypi-all/simple \
                                        -d ${PACKAGE_ML} -r /src/requirements-ml.txt \
    && rm src/version.txt \
    && rm src/requirements-ml.txt \
    && fpm \
              -s dir \
              -t deb \
              --deb-user yexp \
              --deb-group yexp \
              -n ${CODE} \
              -v ${VERSION_NUMBER} \
              --iteration ${BUILD} \
              --description 'CODE template.' \
              -p /build \
              ${PACKAGE_PATH}/=${PACKAGE_PATH} \
              ${PACKAGE_ML}/=${PACKAGE_PATH}${PACKAGE_ML} \
              /src/main.py=${PACKAGE_PATH}/src/main.py \
              /src/queries.yaml=${PACKAGE_PATH}/src/queries.yaml \
              && chown ${CURRENTUSER} /build/*.deb"

docker rm -f $CONTAINER

exit 0
