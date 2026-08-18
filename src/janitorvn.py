import polars as pl
import janitor.polars

def clean_names_vn(self: pl.DataFrame) -> pl.DataFrame:
    df = self.rename(lambda c: c.replace("đ", "d").replace("Đ", "D"))
    return df.clean_names(strip_accents=True)

def make_clean_names_vn(self: pl.Expr) -> pl.Expr:
    return (
        self.str.replace_all("đ", "d")
            .str.replace_all("Đ", "D")
            .make_clean_names(strip_accents=True)
    )

pl.DataFrame.clean_names_vn = clean_names_vn
pl.Expr.make_clean_names_vn = make_clean_names_vn