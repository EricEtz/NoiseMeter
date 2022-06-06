# Noise Meter Code By Eric Etzell
# Version 6.6.2022

import time
import math
import board
import busio
import displayio
import rgbmatrix
import framebufferio
import terminalio
from adafruit_display_shapes.rect import Rect
from adafruit_display_text import label, wrap_text_to_pixels
from analogio import AnalogIn
import ulab
import array
import adafruit_ds1307

#-------------------Microphone Setup------------------------

dc_offset = 0  # DC offset in mic signal - if unusure, leave 0
noise = 100  # Noise/hum/interference in mic signal
samples = 60  # Length of buffer for dynamic level adjustment
top = 12  # Allow dot to go slightly off scale

vol_count = 0  # Frame counter for storing past volume data

lvl = 10  # Current "dampened" audio level
min_level_avg = 0  # For dynamic adjustment of graph low & high
max_level_avg = 90

# Collection of prior volume samples
vol = array.array('H', [0] * samples)

mic_pin = AnalogIn(board.A5)        #plug mic pin into A5

def remap_range(value, leftMin, leftMax, rightMin, rightMax):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    leftSpan = leftMax - leftMin
    rightSpan = rightMax - rightMin

    # Convert the left range into a 0-1 range (int)
    valueScaled = int(value - leftMin) / int(leftSpan)

    # Convert the 0-1 range into a value in the right range.
    return int(rightMin + (valueScaled * rightSpan))


#-------------------Time Setup ------------------------------

i2c = board.I2C()  #uses board.SCL and board.SDA
rtc = adafruit_ds1307.DS1307(i2c)

t = time.struct_time((2022, 4, 19, 20, 45, 0, 0, -1, -1))
#Parameters of time: year(int),month(1-12),day(day of month),hour(0-23),...
# ...minute(0-59),second(0-61),day of week (0monday - 6sunday),day of year (-1 is unknown),...
# ...is it daylight savings (1=yes 0=no, -1=unknown)

if False:
    print("Setting time to:", t)     #set rtc unit time to the above defined time
    rtc.datetime = t

rtc.datetime = t
print("Current time:", t)       #print out the current time


#-------------------LED Setup -------------------------------

disp_delay_ns = 125000000 #0.125s, 125ms display refresh rate

calib_mode = False          #not in calibration mode

#10 blocks of color, used in drawing function
num_panels = 10                      #10 panels

#info for declaring the matrix
bit_depth = 1                           #Color Bit Depth of 1
base_width = 32                         #boards are 32 pixels wide
base_height = 16                        #boards are 16 pixels tall
chain_across = 5                        #5 boards across
tile_down = 1                           #1 board down, aka single line
serpentine = False                      #boards are not serp. (doesn't matter)

is_segmented = True                     #boards are segmented... not sure. doesn't see use

#calculating overall display information
chain_width = base_width * chain_across #chain width is 32*5 pixels
chain_height = base_height * tile_down  #height is 16*1 = 16 pixels
addr_pins = [board.A0, board.A1, board.A2]        #address pins from metro m4
rgb_pins = [board.D2, board.D3, board.D4, board.D5, board.D6, board.D7] #rgb pins from m4
clock_pin = board.A4    #standard clk pin for metro m4
latch_pin = board.D10   #standard latch pin for m4
oe_pin = board.D9       #standard oe pin for m4

disp_height = chain_width   #full height of the display is 32*5
disp_width = chain_height   #full width of the display is 16


#define the stuff that shows on boot
boot_text = "Loading..."                #define the text on bootup
boot_font = terminalio.FONT             #use the font terminalIO
boot_fgcol = 0xFF0000                   #foreground color (white)
boot_bgcol = 0x0000FF                   #background color (blue)


boot_label = label.Label(           #boot sequence
	boot_font,                          #use boot font
	text=boot_text,                     #use boot text (declared above)
	color=boot_fgcol,                   #text color is foreground color
	background_color=boot_bgcol,        #background color is bkgrd color
	scale=2,                            #scale (font size) is 2
	padding_top=8,                      #8 pixels padding on top
	padding_bottom=8,                   #8 pixels padding on bottom
	padding_right=12,                   #12 " right
	padding_left=12,                    #12 " left
	anchor_point = (0.5, 0.5),          #anchor point, where the text starts
    label_direction = "DWR",            #label direction is downward
	anchored_position = (disp_width // 2, disp_height // 2) #in the center of the display
	)

#----------------LEDs are setup, now initialize them------------------------------------------------------

barHeight = 16                  #make 10 colored bars, each of height 16 for a 160 LED display
barWidth = 16                   #bar width is 16

displayio.release_displays()    #clear the display completely

matrix = rgbmatrix.RGBMatrix(           #define the RGB matrix from the established values
                width=chain_width,
                height=chain_height,
                bit_depth=bit_depth,
                rgb_pins=rgb_pins,
                addr_pins=addr_pins,
                clock_pin=clock_pin,
                latch_pin=latch_pin,
                output_enable_pin=oe_pin,
                tile=tile_down, serpentine=serpentine,
            )

#now that the display is set up and ready to go, we can display some stuff on it.

display = framebufferio.FramebufferDisplay(matrix, auto_refresh=True, rotation=270)


#start by displaying the boot label: this is of type label.label()
display.show(boot_label)

#display the boot label for 7 seconds
time.sleep(3)


mainbar = displayio.Group() # The Main Display Group ----------------

#Below, the main bar display is defined. This is the colored bars

#-------------------------------------------------------------------------------------------------------

def dbLevel(n):                         #here, the dbLevel is defined as being "n".
    try:                                #This code prints out the bars up to n
        for i in range(0,10):                #for a value of i between 0 and 10
            mainbar[i].hidden = (i >= n)    #the main bar display group at i is hidden if i is greater than the dbLevel
    except ValueError:                      #basically, bar 7 is turned off if dbLevel is less than 7
        pass

db10= displayio.Group(x=0, y=0)                 #create a group for each db level.
db9 = displayio.Group(x=0, y=1 * barHeight)     #These are empty groups along the display
db8 = displayio.Group(x=0, y=2 * barHeight)     #a call for db4 will display 3 bars
db7 = displayio.Group(x=0, y=3 * barHeight)     #bar Height is 1/10th of display height
db6 = displayio.Group(x=0, y=4 * barHeight)     #db1 starts at height 0
db5 = displayio.Group(x=0, y=5 * barHeight)     #db2 starts at height 16
db4 = displayio.Group(x=0, y=6 * barHeight)     #db3 starts at height 2*16 = 32
db3 = displayio.Group(x=0, y=7 * barHeight)
db2 = displayio.Group(x=0, y=8 * barHeight)
db1 = displayio.Group(x=0, y=9 * barHeight)

#this part of the code colors the bars. first 3 are green, then yellow, then red
for i in range(0,2):      #how many sub-blocks do you want
    db1.append(Rect( 0, i * 8, barWidth, 7, fill=0x00FF00))         #append each group, to have a color.
    db2.append(Rect( 0, i * 8, barWidth, 7, fill=0x00FF00))         #each group ends up being a rectangle with ...
    db3.append(Rect( 0, i * 8, barWidth, 7, fill=0x00FF00))         #position defined by the function
    db4.append(Rect( 0, i * 8, barWidth, 7, fill=0xFFA500))
    db5.append(Rect( 0, i * 8, barWidth, 7, fill=0xFFA500))         #bar width is 16
    db6.append(Rect( 0, i * 8, barWidth, 7, fill=0xFFA500))         #sub-block height is 8 pixles
    db7.append(Rect( 0, i * 8, barWidth, 7, fill=0xFFA500))         #only color the first 7
    db8.append(Rect( 0, i * 8, barWidth, 7, fill=0xFF0000))         #fill describes the color
    db9.append(Rect( 0, i * 8, barWidth, 7, fill=0xFF0000))
    db10.append(Rect(0, i * 8, barWidth, 7, fill=0xFF0000))

mainbar.append(db1)     #iteratively add each rectangle, starting with green and ending with the red ones.
mainbar.append(db2)
mainbar.append(db3)
mainbar.append(db4)
mainbar.append(db5)
mainbar.append(db6)
mainbar.append(db7)
mainbar.append(db8)
mainbar.append(db9)
mainbar.append(db10)


#-------------------------------------------------------------------------------------
#The main bar has been defined. The display is a full color. if you call mainbar right now, it will display the full load


#this bit of code below shows the full bar spectrum
if not calib_mode:              #because calib_mode is false at beginning, we enter this loop
    display.show(mainbar)       #show the main bar on the display. This is the first time it's written to the display


num_panels_lit = 0


#--------------------------------------------LED and Microphone Combination-----------------------------

while True:                         #this is the operation loop of the device. Refresh screen, keep looping.

    n = t(hour)         #define n as what hour it is
    if n>8 || n<20:     #if it's during operation hours, run the code

        time.sleep(0.03)

        #-------------------------------Mic stuff-------------------------------------------------

        n = int((mic_pin.value / 65536) * 1000)  # 10-bit ADC format of noise signal
        n = abs(n - 512 - dc_offset)  # Center on zero

        if n >= noise:  # Remove noise/hum from noise signal
            n = n - noise

        # "Dampened" reading (else looks twitchy) - divide by 8 (2^3)
        lvl = int(((lvl * 7.6) + n) / 8)

        # Calculate bar height based on dynamic min/max levels (fixed point):
        height = top * (lvl - min_level_avg) / (max_level_avg - min_level_avg)

        # Clip output
        if height < 0:
            height = 0
        elif height > top:
            height = top

        #-------------------------------End microphone stuff ------------------------------


        if calib_mode:                          #if you're in calibration mode
            boot_label.text =  "{:.5f}V, {:.1f}".format(voltage_db, leq_disp_val)   #display voltage & display value
            print(voltage_db)       #print out the voltage in dB

        else:	                            # if you aren't in calibration mode and there are some panels to light
            dbLevel(height-2)             #call dbLevel with num panels, which lights those panels
            #print(num_panels_lit)               # print how many panels should be lit



        #done
