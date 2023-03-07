#!/bin/bash
set -e 
set -o pipefail

SOURCE_DIR="$1"
PUBLISH_DIR="$2"
SIGNFILE_DIR="$3"

DIST="all"
COMP="main"

echo "Creating APT repository in $SOURCE_DIR..."

cd $SOURCE_DIR 

count=`find $SOURCE_DIR -name '*.deb' | wc -l`;
if [ $count == 0 ];
then
echo "No files to process";
exit 1;
fi

for f in $(find $SOURCE_DIR -mindepth 2 -name '*.deb' ); do mv -n "$f" $SOURCE_DIR/; done;
rm -rf dists
rm -rf pool

mkdir -p pool/$COMP

mv *.deb pool/$COMP

export PATH=/usr/intel/pkgs/gtar/1.26/bin:/localdisk/dpkg/usr/bin:/localdisk/perl-5.18.2/bin:$PATH; 
export PERL5LIB=/localdisk/perl-5.18.2/lib:/localdisk/perl-5.18.2/lib/5.18.2:/localdisk/dpkg/usr/lib/perl5/vendor_perl/5.10.0;

for arch in all i386 amd64 ; do
    binary_arch="dists/$DIST/$COMP/binary-$arch"
    mkdir -p $binary_arch
	
    dpkg-scanpackages --multiversion --arch $arch pool/$COMP > $binary_arch/Packages
    cat $binary_arch/Packages | gzip -9c > $binary_arch/Packages.gz
    cat $binary_arch/Packages | bzip2    > $binary_arch/Packages.bz2
done

PKGS_ALL=$COMP/binary-all/Packages
PKGS_ALL_WC=`wc -c dists/$DIST/${PKGS_ALL} | cut -d " " -f1`
PKGS_ALL_WC_GZ=`wc -c dists/$DIST/${PKGS_ALL}.gz | cut -d " " -f1`
PKGS_ALL_WC_BZ2=`wc -c dists/$DIST/${PKGS_ALL}.bz2 | cut -d " " -f1`

PKGS_I386=$COMP/binary-i386/Packages
PKGS_I386_WC=`wc -c dists/$DIST/${PKGS_I386} | cut -d " " -f1`
PKGS_I386_WC_GZ=`wc -c dists/$DIST/${PKGS_I386}.gz | cut -d " " -f1`
PKGS_I386_WC_BZ2=`wc -c dists/$DIST/${PKGS_I386}.bz2 | cut -d " " -f1`

PKGS_AMD64=$COMP/binary-amd64/Packages
PKGS_AMD64_WC=`wc -c dists/$DIST/${PKGS_AMD64} | cut -d " " -f1`
PKGS_AMD64_WC_GZ=`wc -c dists/$DIST/${PKGS_AMD64}.gz | cut -d " " -f1`
PKGS_AMD64_WC_BZ2=`wc -c dists/$DIST/${PKGS_AMD64}.bz2 | cut -d " " -f1`

RELEASE_FILE="$SOURCE_DIR/dists/$DIST/Release"
DETACHED_SIGNATURE="$SOURCE_DIR/dists/$DIST/Release.gpg"
CLEARSIGN_FILE="$SOURCE_DIR/dists/$DIST/InRelease"

cat > $RELEASE_FILE << EOF
Architectures: all 386 amd64
Codename: $DIST
Components: $COMP
Date: `date -R -u`
Origin: Intel Corporation
Suite: $DIST
MD5Sum:
 `md5sum dists/$DIST/${PKGS_ALL} | cut -d " " -f1` ${PKGS_ALL_WC} ${PKGS_ALL}
 `md5sum dists/$DIST/${PKGS_ALL}.gz | cut -d " " -f1` ${PKGS_ALL_WC_GZ} ${PKGS_ALL}.gz
 `md5sum dists/$DIST/${PKGS_ALL}.bz2 | cut -d " " -f1` ${PKGS_ALL_WC_BZ2} ${PKGS_ALL}.bz2
 `md5sum dists/$DIST/${PKGS_AMD64} | cut -d " " -f1` ${PKGS_AMD64_WC} ${PKGS_AMD64}
 `md5sum dists/$DIST/${PKGS_AMD64}.gz | cut -d " " -f1` ${PKGS_AMD64_WC_GZ} ${PKGS_AMD64}.gz
 `md5sum dists/$DIST/${PKGS_AMD64}.bz2 | cut -d " " -f1` ${PKGS_AMD64_WC_BZ2} ${PKGS_AMD64}.bz2
 `md5sum dists/$DIST/${PKGS_I386} | cut -d " " -f1` ${PKGS_I386_WC} ${PKGS_I386}
 `md5sum dists/$DIST/${PKGS_I386}.gz | cut -d " " -f1` ${PKGS_I386_WC_GZ} ${PKGS_I386}.gz
 `md5sum dists/$DIST/${PKGS_I386}.bz2 | cut -d " " -f1` ${PKGS_I386_WC_BZ2} ${PKGS_I386}.bz2
SHA1:
 `sha1sum dists/$DIST/${PKGS_ALL} | cut -d " " -f1` ${PKGS_ALL_WC} ${PKGS_ALL}
 `sha1sum dists/$DIST/${PKGS_ALL}.gz | cut -d " " -f1` ${PKGS_ALL_WC_GZ} ${PKGS_ALL}.gz
 `sha1sum dists/$DIST/${PKGS_ALL}.bz2 | cut -d " " -f1` ${PKGS_ALL_WC_BZ2} ${PKGS_ALL}.bz2
 `sha1sum dists/$DIST/${PKGS_AMD64} | cut -d " " -f1` ${PKGS_AMD64_WC} ${PKGS_AMD64}
 `sha1sum dists/$DIST/${PKGS_AMD64}.gz | cut -d " " -f1` ${PKGS_AMD64_WC_GZ} ${PKGS_AMD64}.gz
 `sha1sum dists/$DIST/${PKGS_AMD64}.bz2 | cut -d " " -f1` ${PKGS_AMD64_WC_BZ2} ${PKGS_AMD64}.bz2
 `sha1sum dists/$DIST/${PKGS_I386} | cut -d " " -f1` ${PKGS_I386_WC} ${PKGS_I386}
 `sha1sum dists/$DIST/${PKGS_I386}.gz | cut -d " " -f1` ${PKGS_I386_WC_GZ} ${PKGS_I386}.gz
 `sha1sum dists/$DIST/${PKGS_I386}.bz2 | cut -d " " -f1` ${PKGS_I386_WC_BZ2} ${PKGS_I386}.bz2
SHA256:
 `sha256sum dists/$DIST/${PKGS_ALL} | cut -d " " -f1` ${PKGS_ALL_WC} ${PKGS_ALL}
 `sha256sum dists/$DIST/${PKGS_ALL}.gz | cut -d " " -f1` ${PKGS_ALL_WC_GZ} ${PKGS_ALL}.gz
 `sha256sum dists/$DIST/${PKGS_ALL}.bz2 | cut -d " " -f1` ${PKGS_ALL_WC_BZ2} ${PKGS_ALL}.bz2
 `sha256sum dists/$DIST/${PKGS_AMD64} | cut -d " " -f1` ${PKGS_AMD64_WC} ${PKGS_AMD64}
 `sha256sum dists/$DIST/${PKGS_AMD64}.gz | cut -d " " -f1` ${PKGS_AMD64_WC_GZ} ${PKGS_AMD64}.gz
 `sha256sum dists/$DIST/${PKGS_AMD64}.bz2 | cut -d " " -f1` ${PKGS_AMD64_WC_BZ2} ${PKGS_AMD64}.bz2
 `sha256sum dists/$DIST/${PKGS_I386} | cut -d " " -f1` ${PKGS_I386_WC} ${PKGS_I386}
 `sha256sum dists/$DIST/${PKGS_I386}.gz | cut -d " " -f1` ${PKGS_I386_WC_GZ} ${PKGS_I386}.gz
 `sha256sum dists/$DIST/${PKGS_I386}.bz2 | cut -d " " -f1` ${PKGS_I386_WC_BZ2} ${PKGS_I386}.bz2
SHA512:
 `sha512sum dists/$DIST/${PKGS_ALL} | cut -d " " -f1` ${PKGS_ALL_WC} ${PKGS_ALL}
 `sha512sum dists/$DIST/${PKGS_ALL}.gz | cut -d " " -f1` ${PKGS_ALL_WC_GZ} ${PKGS_ALL}.gz
 `sha512sum dists/$DIST/${PKGS_ALL}.bz2 | cut -d " " -f1` ${PKGS_ALL_WC_BZ2} ${PKGS_ALL}.bz2
 `sha512sum dists/$DIST/${PKGS_AMD64} | cut -d " " -f1` ${PKGS_AMD64_WC} ${PKGS_AMD64}
 `sha512sum dists/$DIST/${PKGS_AMD64}.gz | cut -d " " -f1` ${PKGS_AMD64_WC_GZ} ${PKGS_AMD64}.gz
 `sha512sum dists/$DIST/${PKGS_AMD64}.bz2 | cut -d " " -f1` ${PKGS_AMD64_WC_BZ2} ${PKGS_AMD64}.bz2
 `sha512sum dists/$DIST/${PKGS_I386} | cut -d " " -f1` ${PKGS_I386_WC} ${PKGS_I386}
 `sha512sum dists/$DIST/${PKGS_I386}.gz | cut -d " " -f1` ${PKGS_I386_WC_GZ} ${PKGS_I386}.gz
 `sha512sum dists/$DIST/${PKGS_I386}.bz2 | cut -d " " -f1` ${PKGS_I386_WC_BZ2} ${PKGS_I386}.bz2
EOF

echo "Publishing build results from $SOURCE_DIR to $PUBLISH_DIR"

mv 'dists' $PUBLISH_DIR
mv 'pool' $PUBLISH_DIR

echo "Done"

