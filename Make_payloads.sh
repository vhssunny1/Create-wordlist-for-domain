# wordlist from waybackurls and github-endpoints, JS scan

mkdir $1
cd $1
echo $1 | waybackurls |grep -v "*" | grep -v "@" | grep -v "," | grep -v -e '^$' | tee -a $1-wordlist-master.txt
cat $1-wordlist-master.txt | sort -u | unfurl paths |  sed "s/\///1" | sort -u | grep -v '.jpg$' | grep -v '.jpeg$'| grep -v '.png$' | grep -v '.gif$'| grep -v -e '^$' | tee -a $1-wordlist.txt
cat $1-wordlist.txt | ./sprawl.py -s | tee -a $1-payloads.txt

#cat $1-wordlist.txt | sort -u | tee -a $1-payloads.txt
#rm $1-wordlist.txt
#rm $1-wordlist-master.txt


python3 /github-endpoints.py -d $1 | grep -a -i $1 | tee -a $1.github.txt
cat $1.github.txt |  /home/hari/submax/./sprawl.py -s |  tee -a $1-payloads.txt

cat $1-payloads.txt  | sort -u | tee -a $1-final-payloads.txt
rm $1.github.txt
rm $1-wordlist.txt
rm $1-payloads.txt
