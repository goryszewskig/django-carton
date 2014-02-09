from decimal import Decimal

from carton import settings as carton_settings


def get_product_model():
    """
    Returns the Product model that is used by this cart.
    """
    from django.db.models import get_model

    try:
        app_label, model_name = carton_settings.CART_PRODUCT_MODEL.split('.')
    except ValueError:
        raise ImproperlyConfigured("CART_PRODUCT_MODEL must be of the form 'app_label.model_name'")
    product_model = get_model(app_label, model_name)
    if product_model is None:
        raise ImproperlyConfigured("CART_PRODUCT_MODEL refers to model '%s' that has not been installed" % carton_settings.CART_PRODUCT_MODEL)
    return product_model


class CartItem(object):
    """
    A cart item, with the associated product, its quantity and its price.
    """
    def __init__(self, product, quantity, price):
        self.product = product
        self.quantity = int(quantity)
        self.price = Decimal(str(price))

    def __repr__(self):
        return u'CartItem Object (%s)' % self.product

    def to_dict(self):
        return {
            'product_pk': self.product.pk,
            'quantity': self.quantity,
            'price': str(self.price),
        }

    @property
    def subtotal(self):
        """
        Subtotal for the cart item.
        """
        return self.price * self.quantity


class Cart(object):
    """
    A cart that lives in the session.
    """
    def __init__(self, session, session_key=None, model=None):
        self._items_dict = {}
        self.session = session
        self.session_key = session_key or carton_settings.CART_SESSION_KEY
        self.model = model or get_product_model()

        # If there is already a cart data in session, we extract it
        if self.session_key in self.session:
            session_data = self.session[self.session_key]
            products = dict([(p.pk, p) for p in self.get_queryset([ci['product_pk'] for ci in session_data])])
            for item in session_data:
                product = products.get(item['product_pk'])
                if product:
                    self._items_dict[product.pk] = CartItem(product, item['quantity'], Decimal(item['price']))

    def __contains__(self, product):
        """
        Checks if the given product is in the cart.
        """
        return product in self.products

    def get_queryset(self, item_pk_list):
        """
        Returns a queryset representing the products currently in cart.
        Can be subclassed to provide finer control over which products are returned.
        """
        if item_pk_list:
            return self.model.objects.filter(pk__in=item_pk_list)
        return self.model.objects.none()

    def update_session(self):
        """
        Serializes the cart data, saves it to session and marks session as modified
        """
        self.session[self.session_key] = self.items_serializable
        self.session.modified = True

    def add(self, product, price=None, quantity=1):
        """
        Adds or creates products in cart. For an existing product,
        the quantity is increased and the price is ignored.
        """
        quantity = int(quantity)
        if quantity < 1:
            raise ValueError('Quantity must be at least 1 when adding to cart')
        if product in self.products:
            self._items_dict[product.pk].quantity += quantity
        else:
            if price == None:
                raise ValueError('Missing price when adding to cart')
            self._items_dict[product.pk] = CartItem(product, quantity, price)
        self.update_session()

    def remove(self, product):
        """
        Removes the product.
        """
        if product in self.products:
            del self._items_dict[product.pk]
            self.update_session()

    def remove_single(self, product):
        """
        Removes a single product by decreasing the quantity.
        """
        if product in self.products:    
            if self._items_dict[product.pk].quantity <= 1:
                # There's only 1 product left so we drop it
                del self._items_dict[product.pk]
            else:
                self._items_dict[product.pk].quantity -= 1
            self.update_session()

    def clear(self):
        """
        Removes all items.
        """
        self._items_dict = {}
        self.update_session()

    def set_quantity(self, product, quantity):
        """
        Sets the product's quantity.
        """
        quantity = int(quantity)
        if quantity < 0:
            raise ValueError('Quantity must be positive when updating cart')
        if product in self.products:
            self._items_dict[product.pk].quantity = quantity
            if self._items_dict[product.pk].quantity < 1:
                del self._items_dict[product.pk]
            self.update_session()

    @property
    def items(self):
        """
        The list of cart items.
        """
        return self._items_dict.values()

    @property
    def items_serializable(self):
        """
        The list of items formatted for serialization.
        """
        return [item.to_dict() for item in self.items]

    @property
    def count(self):
        """
        The number of items in cart, that's the sum of quantities.
        """
        return sum([item.quantity for item in self.items])

    @property
    def unique_count(self):
        """
        The number of unique items in cart, regardless of the quantity.
        """
        return len(self._items_dict)

    @property
    def is_empty(self):
        return self.unique_count == 0

    @property
    def products(self):
        """
        The list of associated products.
        """
        return [item.product for item in self.items]

    @property
    def total(self):
        """
        The total value of all items in the cart.
        """
        return sum([item.subtotal for item in self.items])
