import asyncio

from sqlalchemy import text

from app.database import migration_engine

SRID_4326_SRTEXT = (
    'GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,'
    'AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,'
    'AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],'
    'AUTHORITY["EPSG","4326"]]'
)
SRID_4326_PROJ4 = "+proj=longlat +datum=WGS84 +no_defs"


async def main():
    async with migration_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO spatial_ref_sys (srid, auth_name, auth_srid, srtext, proj4text) "
                "VALUES (:srid, 'EPSG', :srid, :srtext, :proj4) "
                "ON CONFLICT (srid) DO NOTHING"
            ),
            {"srid": 4326, "srtext": SRID_4326_SRTEXT, "proj4": SRID_4326_PROJ4},
        )
        n = (await conn.execute(text("SELECT count(*) FROM spatial_ref_sys"))).scalar()
        print("spatial_ref_sys rows:", n)


if __name__ == "__main__":
    asyncio.run(main())
