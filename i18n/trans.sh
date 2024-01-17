if [ "$#" -ne 2 ]
then
    echo "Urage: trans <language> <destination>"
    exit
else
    lang=$1
    dest=$2
    trubar --conf $lang/trubar-config.yaml translate -s ../orangecanvas -d $dest/orangecanvas --static $lang/static $lang/msgs.jaml
fi

