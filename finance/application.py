import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    rows = db.execute("""
        SELECT symbol, SUM(shares) as TotalShares
        FROM history
        WHERE user_id=?
        GROUP BY symbol
        Having TotalShares > 0;
    """, session["user_id"])

    portfolio = []
    net_total = 0
    for row in rows:
        stock_search = lookup(row["symbol"])
        portfolio.append({
            "name": stock_search["name"],
            "symbol": stock_search["symbol"],
            "shares": row["TotalShares"],
            "price": stock_search["price"],
            "total": usd(stock_search['price'] * row["TotalShares"])
        })
        net_total += stock_search['price'] * row["TotalShares"]

    rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
    current_cash = rows[0]["cash"]
    net_total += current_cash

    return render_template("index.html", portfolio=portfolio, current_cash=usd(current_cash), net_total=usd(net_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html")
    else:
        if request.form.get("stock") == "":
            return apology("invalid symbol. please try again.", 403)
        elif not request.form.get("shares").isdigit():
            return apology("invalid number of shares. please try again.", 403)
        else:
            number_of_shares = request.form.get("shares")
            stock_symbol = request.form.get("stock").upper()
            stock_search = lookup(stock_symbol)
            if stock_search is None:
                return apology("invalid symbol. please try again.", 403)
            rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
            cash = rows[0]["cash"]
            purchase_price = stock_search['price'] * int(number_of_shares)
            updated_cash = cash - purchase_price
            if updated_cash < 0:
                return apology("you cannot afford this purchase. please try again.", 403)
            db.execute("UPDATE users SET cash=? WHERE id=?", (updated_cash, session["user_id"]))
            db.execute("""
                INSERT INTO history (user_id, symbol, shares, price)
                VALUES (?, ?, ?, ?);
            """, (session["user_id"], stock_search['symbol'], int(number_of_shares), stock_search['price']))
            flash("Purchase Successful!")
            return redirect("/")



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    return apology("TODO")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        if request.form.get("stock") == "":
            return apology("you must enter a valid stock symbol.", 403)
        else:
            stock_symbol = request.form.get("stock").upper()
            stock_search = lookup(stock_symbol)
            if stock_search is None:
                return apology("you must enter a valid stock symbol.", 403)
            return render_template("quoted.html", stock_info={"name": stock_search['name'], "symbol": stock_search['symbol'], "price": usd(stock_search['price'])})


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        if request.form.get("username") == "" or request.form.get("password") == "":
            return apology("registration error. please enter a username and a password.", 403)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("registration error. ensure both passwords match.", 403)
        else:
            username = request.form.get("username")
            hashing = generate_password_hash(request.form.get("password"))
            try:
                p_key = db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", (username, hashing))
            except:
                return apology("username already exists. please try again.", 403)
            session["user_id"] = p_key
            return redirect("/")




@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        rows = db.execute("""
            SELECT symbol FROM history
            WHERE user_id=?
            GROUP BY symbol
            HAVING SUM(shares) > 0;
        """, session["user_id"])
        return render_template("sell.html", symbols=[ row["symbol"] for row in rows ])
    else:
        symbol = request.form.get("symbol").upper()
        number_of_shares = request.form.get("shares")
        if number_of_shares == "" or number_of_shares == 0:
            return apology("you must enter a valid share amount. please try again.", 403)
        number_of_shares = int(number_of_shares)
        stock_search = lookup(symbol)

        if stock_search is None:
            return apology("invalid symbol. please try again", 403)

        rows = db.execute("""
            SELECT symbol, SUM(shares) as TotalShares FROM history
            WHERE user_id=?
            GROUP BY symbol
            HAVING TotalShares > 0;
        """, session["user_id"])

        for row in rows:
            if row["symbol"] == symbol:
                if number_of_shares > row['TotalShares']:
                    return apology("too many shares selected. please try again", 403)

        # Create a variables needed like current cash, selling price, and updated cash
        rows = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])
        cash = rows[0]["cash"]
        sell_price = number_of_shares * stock_search["price"]
        updated_cash = cash + sell_price

        # update the database with the new cash amount after the sale
        db.execute("UPDATE users SET cash=? WHERE id=?", (updated_cash, session["user_id"]))

        # update the database with the selling of the shares
        db.execute("""
            INSERT INTO history (user_id, symbol, shares, price)
            VALUES (?, ?, ?, ?);
        """, (session["user_id"], stock_search["symbol"], number_of_shares * -1, stock_search["price"]) )

        flash("Stocks Successfully Sold!")
        return redirect("/")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
