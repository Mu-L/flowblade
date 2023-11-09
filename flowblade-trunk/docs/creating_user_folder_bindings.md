
## Building Python 3 bindings to use with repo installation

This is a rough guide on how install and run self created MLT bindinds with Flowblade install from repository.

Please create pull request against this document if you have corrections or additions to improve this guide.

### Install Flowblade from repository
See [here](./INSTALLING.md).

### Install MLT build dependencies
Here is list of Ubuntu dependencies. There could be some omissions, please file pull request to update the list if something is found to be missing.

```bash
sudo apt-get install git swig python3-dev python3-numpy libxml2-dev libsdl-dev libavdevice-dev libswscale-dev libvorbis-dev libsamplerate-dev frei0r-plugins-dev libdv-dev libavformat-dev libquicktime-dev libsox-dev libjack-dev ladspa-sdk
```

### Create work directory 

Let's call this directory **\<ROOT_DIR\>**. Open terminal in this directory

### Clone MLT repository
```bash
git clone https://github.com/mltframework/mlt.git
```

### Configure build
```bash
cd mlt
./configure --prefix=<ROOT_DIR>/build --enable-gpl --enable-gpl3 --swig-languages=python
```

### Build MLT and bindings
 ```bash
make 
make install
```  

#### new mlt with cmake

In 2023, mlt builds with cmake; in that case, to build mlt:

```bash
cd mlt
mkdir build
cd build
cmake .. -DSWIG_PYTHON=ON -DGPL=ON -DGPL3=ON
make
```
(unsure how to set install path for `make install` here; so this type of build will probably not work with the launch script as given below, without modifications).

### Set up bindings

1. Copy *mlt.py* and *_mlt.so* from  *\<ROOT_DIR\>/mlt/src/swig/python* into  *../flowblade-trunk* where your repository version Flowblade is installed.
1. Create launch script in **\<ROOT_DIR\>** to set up MLT variables correctly on launch.

 ```bash
#!/bin/sh

# Set MLT environment variables to point
# where you have the binaries and libraries
# so MLT finds them runtime.
WORK_DIR=<ROOT_DIR>

INSTALL_DIR=$WORK_DIR/build
export PATH=$WORK_DIR/bin:$PATH

export MLT_REPOSITORY=$INSTALL_DIR/lib/mlt
export MLT_DATA=$INSTALL_DIR/share/mlt
export MLT_PROFILES_PATH=$INSTALL_DIR/share/mlt/profiles
export LD_LIBRARY_PATH=$INSTALL_DIR/lib:$LD_LIBRARY_PATH

# Launch repository Flowblade
/home/path/to/your/repository/install/flowblade-trunk/flowblade
``` 

Launch Flowblade with the script above.
