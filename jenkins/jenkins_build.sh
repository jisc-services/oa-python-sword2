#!/bin/bash
######################################################################
# Jenkins script for Building SWORD2 library.
#
# Params:
#   1. Build Live: one of [ true | false ]
#   2. Run tests: one of [ true | false ]
#   3. Overwrite live pypi package: one of [ true | false ]
#
######################################################################
echo -e "\n---- Jenkins Build Script ----\n"
PKG_NAME=sword2

#### HANDLE PARAMETERS ####

# Server environment defaults to 'test' if no param passed
BUILD_LIVE=${1-false}
echo "Build-live: $BUILD_LIVE."

ROUTER_RUN_TESTS=${2-false}
echo "Run tests: $ROUTER_RUN_TESTS."

OVERWRITE_PKG=${3-false}
echo "Overwrite PyPi package: $OVERWRITE_PKG."

# PyPi URL depends on whether Building Live or Dev
if [ $BUILD_LIVE = true ]; then
  PYPI_HOST=live_pypi.XXXX.YYYY.jisc.ac.uk   # URL for Live package deposits
  TARGET=LIVE
else
  PYPI_HOST=dev_pypi.XXXX.YYYY.jisc.ac.uk    # URL for Dev package deposits
  TARGET=DEV
fi
PYPI_URL=http://${PYPI_HOST}

#### DIAGNOSITICS ####
echo -e "\n*** Diagnostics ***"
echo -e "* Workspace: $WORKSPACE"
echo -e "* Path: $PATH"
echo -e "* Git Branch: $GIT_REF"
echo -e "* Target: $TARGET."
echo -e "* PyPi URL: $PYPI_URL."

echo -e "\n*** Remove old builds"
rm -rf $WORKSPACE/dist

echo -e "\n*** Remove old builder if it exists ***"
rm -rf builder

echo -e "\n*** Create virtual environment ***"
python3 -m venv builder
source builder/bin/activate

# Upgrade pip
#pip install --upgrade pip


echo "Installing setuptools. pywheel & pytest"
pip install --upgrade setuptools wheel twine

if [ $ROUTER_RUN_TESTS = true ]; then
  echo -e "\n*** installing pytest and packages for tests ***"
  pip install pytest
  pip install . --verbose --extra-index-url ${PYPI_URL}/simple/ --trusted-host ${PYPI_HOST}
  # python3 setup.py install

  # echo -e "\n*** Setting MySQL Hostname environment variable ***"
  # export MYSQL_HOST='dr-oa-test-pubrouter.cewhgxkzt0vu.eu-west-1.rds.amazonaws.com'

  echo -e "\n*** Running tests ***"
  pytest $WORKSPACE/$PKG_NAME || exit 1
fi

echo -e "\n*** Building package..."
pip install build
python3 -m build --wheel --verbose
#python3 setup.py bdist_wheel

#cd $WORKSPACE/dist
PACKAGE=$(find ./dist -name '*.whl')
PACKAGE_NAME=$(basename $PACKAGE)

if [ $OVERWRITE_PKG = true ]; then
  echo -e "\n*** Deleting old $TARGET pypi package: $PACKAGE_NAME (if it exists)"
  # Obtain package Name & Version from Package Name, splitting it on '-' chars. Finally reset IFS to default.
  IFS='-'; read -r NAME VERSION IGNORE <<< "$PACKAGE_NAME"; unset IFS
  # Remove specified package (it if exists)
  curl --silent --form ":action=remove_pkg" --form "name=${NAME}" --form "version=${VERSION}" ${PYPI_URL} > /dev/null 2>&1
  #curl --verbose --form ":action=remove_pkg" --form "name=${NAME}" --form "version=${VERSION}" ${PYPI_URL}
fi

echo -e "\n*** Submitting pypi package: $PACKAGE_NAME to $TARGET pypi repository"
# Using single curly brackets here, with ';' terminators causes snippet to run in CURRENT shell, so the `exit 1` works
twine upload -u x -p x --repository-url ${PYPI_URL} "$PACKAGE" || { echo -e "\n!!! failed to upload $TARGET package: $PACKAGE_NAME !!!\n"; exit 1; }

echo -e "\n\n---- End of build script -- for Git Branch: $GIT_REF -- Build-live: $BUILD_LIVE ----\n\n"

# end #
