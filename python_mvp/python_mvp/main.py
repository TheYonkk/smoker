# Python core
from argparse import ArgumentParser
import logging
import sys
import time

# Python extended
import lgpio
import influxdb_client
from influxdb_client.client.write_api import SYNCHRONOUS


# Project

logger = logging.getLogger()
logger.addHandler(logging.StreamHandler(sys.stdout))
logger.setLevel(logging.INFO)


#######################
#      I2C CONFIG     #
#######################

# update frequency of the main control loop
UPDATE_FREQ_HZ = 100

# ADS1115 ADC constants
ADS1115_ADDR = 0b1001000

ADS1115_CONFIG_REGISTER = 0x01
ADS1115_CONVERSION_REGISTER = 0x00

# Configuration bits
START_SINGLE_CONVERSION = 0x8000  # Start a single conversion
MUX_AIN0_SINGLE_ENDED = 0x4000  # MUX = 100 for AIN0
MUX_AIN1_SINGLE_ENDED = 0x5000  # MUX = 101 for AIN1
MUX_AIN2_SINGLE_ENDED = 0x6000  # MUX = 110 for AIN2
MUX_AIN3_SINGLE_ENDED = 0x7000  # MUX = 111 for AIN3
PGA_4_096V = 0x0200  # +/- 4.096V FSR
MODE_SINGLE_SHOT = 0x0100  # Single-shot mode
MODE_CONT_CONVERSION = 0x0000  # Continuous sample mode
DR_128SPS = 0x0080  # Data rate = 128 samples per second
COMP_QUE_DISABLE = 0x0003  # comparator queue, unused

# reading the config register, this bit is 1 when not performing a conversion
OS_NOT_PERFORMING_CONVERSION = 0x8000

#######################
#    SMOKER CONFIG    #
#######################

GPIO_CHIP_NUMBER = 4
HEATING_ELEMENT_OUTPUT_PIN = 17

NUM_SAMPLES_FOR_ADC_AVG = 50

#######################
#   INFLUXDB CONFIG   #
#######################

INFLUXDB_BUCKET = "smoker-pi"
INFLUXDB_ORG = "smoker"
with open("/home/daveyonkers/influx_token", "r") as fp:
    INFLUXDB_TOKEN = fp.read().strip()
INFLUXDB_URL = "http://localhost:8086"


def convert_to_temp_F(adc_reading: float):
    """
    Incorrect, but probably good enough polynomial fit
    """
    return (
        233.39674664
        + 71.37158218 * (-1.05792914 + 0.0001376 * adc_reading)
        - 4.12594504 * (-1.05792914 + 0.0001376 * adc_reading) ** 2
    )


def swap_endianness_16bit(value):
    """Swap endianness of a 16-bit integer."""
    swapped = ((value & 0xFF00) >> 8) | ((value & 0x00FF) << 8)
    return swapped


def convert_signed_16bit_to_int(value):
    """Convert a 16-bit two's complement value to a signed integer."""
    # If the sign bit (15th bit) is set, convert the value to negative
    if value & 0x8000:
        return value - 0x10000
    else:
        return value


def is_conversion_complete(handle):
    res = swap_endianness_16bit(lgpio.i2c_read_word_data(handle, ADS1115_CONFIG_REGISTER))
    return (res & OS_NOT_PERFORMING_CONVERSION) != 0


def sample_adc_channel(adc_handle: int, channel: int, continuous=False):
    """
    continuous not really working, yet :(
    """
    if channel == 0:
        input_mux = MUX_AIN0_SINGLE_ENDED
    elif channel == 1:
        input_mux = MUX_AIN1_SINGLE_ENDED
    elif channel == 2:
        input_mux = MUX_AIN2_SINGLE_ENDED
    elif channel == 3:
        input_mux = MUX_AIN3_SINGLE_ENDED
    else:
        raise ValueError("Channel must be between 0 and 3!")

    mode = MODE_CONT_CONVERSION if continuous else MODE_SINGLE_SHOT

    config = START_SINGLE_CONVERSION | input_mux | PGA_4_096V | mode | DR_128SPS | COMP_QUE_DISABLE

    lgpio.i2c_write_word_data(adc_handle, ADS1115_CONFIG_REGISTER, config)

    # read back config (maybe useful for debuggin)
    timeout = time.time() + 0.1
    complete = False
    while time.time() < timeout:
        if is_conversion_complete(adc_handle):
            complete = True

    if complete:
        raw_reading = lgpio.i2c_read_word_data(adc_handle, 0)
        logger.debug(f"Raw = {raw_reading:04X}")
        logger.debug(f"Swapped = {swap_endianness_16bit(raw_reading):04X}")
        return convert_signed_16bit_to_int(swap_endianness_16bit(raw_reading))


def resample_adc_channel(adc_handle: int) -> int:
    """
    A single channel must already be configured in continuous conversion mode!
    """
    raw_reading = lgpio.i2c_read_word_data(adc_handle, 0)
    logger.debug(f"Raw = {raw_reading:04X}")
    return convert_signed_16bit_to_int(swap_endianness_16bit(lgpio.i2c_read_word_data(adc_handle, 0)))


def main(setpoint: float, always_on: bool):
    """
    Smoke some meats. Just tryna show that we can read in an ADC value, convert it to a temp,
    then control the output of a GPIO controlling the main heating element. A bonus will be
    to log the values to InfluxDB.

    :setpoint: The setpoint of the smoker in Fahrenheit
    :always_on: Force the heating element to always be on
    """
    logger.info(f"Starting main with {setpoint=}")

    db_client = influxdb_client.InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    write_api = db_client.write_api(write_options=SYNCHRONOUS)

    h = lgpio.gpiochip_open(GPIO_CHIP_NUMBER)
    lgpio.gpio_claim_output(h, HEATING_ELEMENT_OUTPUT_PIN)
    adc_handle = lgpio.i2c_open(1, ADS1115_ADDR)

    while True:
        total = 0
        i = 0
        while i < NUM_SAMPLES_FOR_ADC_AVG:
            try:
                total += sample_adc_channel(adc_handle, 0, continuous=False)
                time.sleep(0.1)
            except (lgpio.error,):
                logger.exception("Did an oopsie during a sample. Pushing forward, though!")
                time.sleep(1)

                continue

            i += 1

        res = total / NUM_SAMPLES_FOR_ADC_AVG
        est_temp = convert_to_temp_F(res)
        is_element_on = est_temp < setpoint or always_on

        lgpio.gpio_write(h, HEATING_ELEMENT_OUTPUT_PIN, is_element_on)

        logger.info(f"Averaged ADC sample reading: {res}")
        logger.info(f"Estimated temperature (F):   {est_temp}")
        logger.info(f"Heating element is on:       {is_element_on}")

        # log some stuffs to the database
        p = (
            influxdb_client.Point("smoker_sample")
            .tag("version", "mvp")
            .field("temperature", est_temp)
            .field("adc", res)
            .field("bottom_element_on", is_element_on)
            .field("adc_sample_count", NUM_SAMPLES_FOR_ADC_AVG)
            .field("setpoint", setpoint)
            .field("always_on", always_on)
        )
        write_api.write(bucket=INFLUXDB_BUCKET, org=INFLUXDB_ORG, record=p)


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument(
        "setpoint",
        action="store",
        help="The setpoint of the smoker in Fahrenheit.",
        type=float,
    )
    parser.add_argument(
        "--always-on",
        action="store_true",
        help="Force the heating element to always be on",
    )
    args = parser.parse_args()

    main(setpoint=args.setpoint, always_on=args.always_on)
