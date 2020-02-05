#!/bin/bash

# e97dff
R_FROM=0xe9
G_FROM=0x7d
B_FROM=0xff
# 7dff8b
R_TO=0x7d
G_TO=0xff
B_TO=0x8b

NB_COLOR=22
HTML_PAGE="color.html"

# Convert to decimal
r_from=$(printf "%d" $R_FROM)
g_from=$(printf "%d" $G_FROM)
b_from=$(printf "%d" $B_FROM)
r_to=$(printf "%d" $R_TO)
g_to=$(printf "%d" $G_TO)
b_to=$(printf "%d" $B_TO)

r_step=$(bc -l <<< "($r_to - $r_from) / ($NB_COLOR + 1)")
g_step=$(bc -l <<< "($g_to - $g_from) / ($NB_COLOR + 1)")
b_step=$(bc -l <<< "($b_to - $b_from) / ($NB_COLOR + 1)")

# Write the html page
echo "<html>" > $HTML_PAGE
echo "  <body>" >> $HTML_PAGE

echo "Copy/paste the following color codes:"
#echo $r_step $g_step $b_step
#echo $r_from $g_from $b_from
color_from=$(printf "%X%X%X" $r_from $g_from $b_from)
echo $color_from

for i in $(seq 1 $(( $NB_COLOR - 2)) ); do
  r_new=$(bc <<< "$r_from + $i * $r_step")
  r_new=$(printf "%.0f" $r_new)
  g_new=$(bc <<< "$g_from + $i * $g_step")
  g_new=$(printf "%.0f" $g_new)
  b_new=$(bc <<< "$b_from + $i * $b_step")
  b_new=$(printf "%.0f" $b_new)
  color_new=$(printf "%X%X%X" $r_new $g_new $b_new)
  echo $color_new
  echo "<div style='width: 60px; height: 60px;background-color:$color_new;float: left;'></div>" >> $HTML_PAGE
done

#echo $r_to $g_to $b_to
color_to=$(printf "%X%X%X" $r_to $g_to $b_to)
echo $color_to

# Write the html page
echo "  </body>" >> $HTML_PAGE
echo "</html>" >> $HTML_PAGE

echo "Samples are in color.html"
