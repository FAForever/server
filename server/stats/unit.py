from enum import Enum


class Unit(Enum):

    # ACUs
    AEON_ACU = "ual0001"
    CYBRAN_ACU = "url0001"
    UEF_ACU = "uel0001"
    SERAPHIM_ACU = "xsl0001"

    # ASFs
    CORONA = "uaa0303"
    GEMINI = "ura0303"
    WASP = "uea0303"
    IAZYNE = "xsa0303"

    # Experimentals
    # Aeon
    PARAGON = "xab1401"
    CZAR = "uaa0310"
    GALACTIC_COLOSSUS = "ual0401"
    TEMPEST = "uas0401"
    SALVATION = "xab2307"
    #UEF
    MAVOR = "ueb2401"
    FATBOY = "uel0401"
    NOVAX_CENTER = "xeb2402"
    ATLANTIS = "ues0401"
    #Cybran
    SOUL_RIPPER = "ura0401"
    SCATHIS = "url0401"
    MONKEYLORD = "url0402"
    MEGALITH = "xrl0403"
    #Sera
    YOLONA_OSS = "xsb2401"
    AHWASSA = "xsa0402"
    YTHOTHA = "xsl0401"

    # Transporters
    CHARIOT = "uaa0107"
    ALUMINAR = "uaa0104"
    SKYHOOK = "ura0107"
    DRAGON_FLY = "ura0104"
    C6_COURIER = "uea0107"
    C14_STAR_LIFTER = "uea0104"
    CONTINENTAL = "xea0306"
    VISH = "xsa0107"
    VISHALA = "xsa0104"

    # SACUs
    AEON_SACU = "ual0301"
    CYBRAN_SACU = "url0301"
    UEF_SACU = "uel0301"
    SERAPHIM_SACU = "xsl0301"

    # Engineers
    AEON_T1_ENGINEER = "ual0105"
    AEON_T2_ENGINEER = "ual0208"
    AEON_T3_ENGINEER = "ual0309"
    CYBRAN_T1_ENGINEER = "url0105"
    CYBRAN_T2_ENGINEER = "url0208"
    CYBRAN_T3_ENGINEER = "url0309"
    UEF_T1_ENGINEER = "uel0105"
    UEF_T2_ENGINEER = "uel0208"
    UEF_T2_FIELD_ENGINEER = "xel0209"
    UEF_T3_ENGINEER = "uel0309"
    SERAPHIM_T1_ENGINEER = "xsl0105"
    SERAPHIM_T2_ENGINEER = "xsl0208"
    SERAPHIM_T3_ENGINEER = "xsl0309"

    # Other units
    MERCY = "daa0206"
    FIRE_BEETLE = "xrl0302"
    SALVATION = "xab2307"


ACUS = [
    Unit.AEON_ACU,
    Unit.CYBRAN_ACU,
    Unit.UEF_ACU,
    Unit.SERAPHIM_ACU
]

ASFS = [
    Unit.CORONA,
    Unit.GEMINI,
    Unit.WASP,
    Unit.IAZYNE
]

SACUS = [
    Unit.AEON_SACU,
    Unit.CYBRAN_SACU,
    Unit.UEF_SACU,
    Unit.SERAPHIM_SACU
]

EXPERIMENTALS = [
    Unit.YOLONA_OSS,
    Unit.PARAGON,
    Unit.ATLANTIS,
    Unit.TEMPEST,
    Unit.SCATHIS,
    Unit.MAVOR,
    Unit.CZAR,
    Unit.AHWASSA,
    Unit.YTHOTHA,
    Unit.FATBOY,
    Unit.MONKEYLORD,
    Unit.GALACTIC_COLOSSUS,
    Unit.SOUL_RIPPER,
    Unit.MEGALITH,
    Unit.NOVAX_CENTER,
    Unit.SALVATION
]

TRANSPORTS = [
    Unit.CHARIOT,
    Unit.ALUMINAR,
    Unit.SKYHOOK,
    Unit.DRAGON_FLY,
    Unit.C6_COURIER,
    Unit.C14_STAR_LIFTER,
    Unit.CONTINENTAL,
    Unit.VISH,
    Unit.VISHALA
]

ENGINEERS = [
    Unit.AEON_T1_ENGINEER,
    Unit.AEON_T2_ENGINEER,
    Unit.AEON_T3_ENGINEER,
    Unit.CYBRAN_T1_ENGINEER,
    Unit.CYBRAN_T2_ENGINEER,
    Unit.CYBRAN_T3_ENGINEER,
    Unit.UEF_T1_ENGINEER,
    Unit.UEF_T2_ENGINEER,
    Unit.UEF_T2_FIELD_ENGINEER,
    Unit.UEF_T3_ENGINEER,
    Unit.SERAPHIM_T1_ENGINEER,
    Unit.SERAPHIM_T2_ENGINEER,
    Unit.SERAPHIM_T3_ENGINEER
]
