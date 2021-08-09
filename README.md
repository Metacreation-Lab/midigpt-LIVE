# How to use MMM for Max4Live

Copy this folder to ~/Documents/Max 8/Packages

Then open `MMM-example` in the `MMM-example Project` folder

Select scenes / tracks / clips and push GENERATE

# Building MMM4Live

Run the install.sh script, this should set everything up.
Then Build (press the play button)

NB: MMM needs a .pt model to run, that must be placed in the "models" folder at the root of the repo (see release) 


## for the record 

Type the following commands in the Terminal:

- `git clone git@github.com:jeffreyjohnens/MMM4LIVE.git`
- `cd MMM4LIVE`
- `git submodule update --init --recursive`
- `git submodule sync --recursive`
- `cd source/projects/MMM.compose`
- `cmake -G Xcode .`

(you might need to first install cmake, protobuf and libtorch with homebrew, e.g.)

This should generate a XCode project that you can then open.
Choose the MMM.compose > My Mac scheme 

You need to set the target (for this scheme) to MacOS 10.14 in the build settings (click on the MMM.compose item at the root of the explorer - left panel, then in the Deployment settings).


## Dependencies

The Max externals in this repository are based on Cycling’74’s  [min-devkit](https://github.com/Cycling74/min-devkit).
All dependencies of min-devkit are added as submodules to this repository. 
