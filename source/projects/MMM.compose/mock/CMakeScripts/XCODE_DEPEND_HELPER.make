# DO NOT EDIT
# This makefile makes sure all linkable targets are
# up-to-date with anything they link to
default:
	echo "Do not invoke directly"

# Rules to remove targets that are older than anything to which they
# link.  This forces Xcode to relink the targets from scratch.  It
# does not seem to check these dependencies itself.
PostBuild.mock_kernel.Debug:
/Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/libmock_kernel.dylib:
	/bin/rm -f /Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/libmock_kernel.dylib


PostBuild.mock_kernel.Release:
/Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/libmock_kernel.dylib:
	/bin/rm -f /Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/libmock_kernel.dylib


PostBuild.mock_kernel.MinSizeRel:
/Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/MinSizeRel/libmock_kernel.dylib:
	/bin/rm -f /Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/MinSizeRel/libmock_kernel.dylib


PostBuild.mock_kernel.RelWithDebInfo:
/Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/RelWithDebInfo/libmock_kernel.dylib:
	/bin/rm -f /Users/bltzr/Documents/Max\ 8/Packages/MMM/tests/RelWithDebInfo/libmock_kernel.dylib




# For each target create a dummy ruleso the target does not have to exist
