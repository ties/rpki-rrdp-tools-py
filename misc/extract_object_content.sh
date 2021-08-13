#!/bin/bash
if [[ ! $1 ]]
then
  echo "Pass a directory as argument"
  exit
fi
if [[ ! -d $1 ]]
then
  echo "Not a directory: $1"
  exit
fi

echo "Dumping ASN1 of ROAs"
find $1 \
  -name \*.roa \
  -exec sh -c 'openssl asn1parse -in $1 -inform DER > $1.txt' x {} \;
echo "Dumping Manifests"
find $1 \
  -name \*.mft \
  -exec sh -c 'openssl asn1parse -in $1 -inform DER > $1.txt' x {} \;
echo "Dumping X509 certificates"
find $1 \
  -name \*.cer \
  -exec sh -c 'openssl x509 -in $1 -noout -text -inform DER > $1.txt' x {} \;
echo "Dumping CRLs"
find $1 \
  -name \*.crl \
  -exec sh -c 'openssl crl -in $1 -noout -text -inform DER > $1.txt' x {} \;
echo "Dumping GBRs"
find $1 \
  -name \*.gbr \
  -exec sh -c 'openssl asn1parse -in $1 -inform DER > $1.txt' x {} \;
