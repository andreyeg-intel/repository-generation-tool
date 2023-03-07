#!/bin/bash
set -e 
set -o pipefail

SOURCE_DIR="$1"
PUBLISH_DIR="$2"
SIGNFILE_DIR="$3"

echo "Creating yum repository from $SOURCE_DIR"

cd $SOURCE_DIR

count=`ls -1 *.rpm 2>/dev/null | wc -l`;
if [ $count == 0 ];
then
echo "No files to process";
exit 1;
fi

createrepo -q $SOURCE_DIR

echo "Publishing build results from $SOURCE_DIR to $PUBLISH_DIR"

for f in $(find $SOURCE_DIR -name '*.rpm'); do mv "$f" $PUBLISH_DIR; done;
mv 'repodata' $PUBLISH_DIR

echo "Done"

