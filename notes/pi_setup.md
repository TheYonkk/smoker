# Pi 5 Setup Notes


## Enabling i2c

First, install `raspi-config` and `i2c-tools`, then go through the straightforward setup to enable the i2c driver/peripheral on boot

```bash
sudo apt-get install raspi-config i2c-tools
sudo raspi-config
```

Then, if an i2c device is attached, you should be able to run `i2cdetect` to see its address. `-y` skips a silly warning prompt (warnings are for suckers, just full send it) and `1` is the i2c device index.

```bash
i2cdetect -y 1
```

```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- -- 
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
40: -- -- -- -- -- -- -- -- 48 -- -- -- -- -- -- -- 
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
70: -- -- -- -- -- -- -- --  
```

### Notes

* After doing the above steps, I wanted to learn what it was actually doing under the hood. I guess it just sets `dtparam=i2c_arm=on` in `/boot/firmware/config.txt` if it wasn't already (mine seems to likely have been enabled already, as audio and SPI are enabled but I did not explicitly enable them). Additionally, it adds an `i2c` user group that has access to the `/dev/i2c*` devices, then adds you to it. This is so you can run i2c commands without `sudo`. 
