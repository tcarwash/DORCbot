def isvalidgrid(locator):
    # Is this a valid Maidenhead grid?
    # Format checking from pyhamtools (https://github.com/dh1tw/pyhamtools)
    try:
        locator = locator.upper()
        if len(locator) == 5 or len(locator) < 4:
            raise ValueError
        if ord(locator[0]) > ord('R') or ord(locator[0]) < ord('A'):
            raise ValueError

        if ord(locator[1]) > ord('R') or ord(locator[1]) < ord('A'):
            raise ValueError

        if ord(locator[2]) > ord('9') or ord(locator[2]) < ord('0'):
            raise ValueError

        if ord(locator[3]) > ord('9') or ord(locator[3]) < ord('0'):
            raise ValueError

        if len(locator) == 6:
            if ord(locator[4]) > ord('X') or ord(locator[4]) < ord('A'):
                raise ValueError
            if ord(locator[5]) > ord('X') or ord(locator[5]) < ord('A'):
                raise ValueError
        return True
    except:
        return False
