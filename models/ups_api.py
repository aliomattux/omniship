import base64
from ups import ShipmentConfirm, ShipmentAccept, ShipmentVoid, PyUPSException
from openerp.osv import osv, fields
from lxml import etree
from lxml.builder import E
from openerp.tools.translate import _
from PIL import Image
import cStringIO
from cStringIO import StringIO
from tempfile import NamedTemporaryFile
import subprocess

class OmnishipProcessor(osv.osv_memory):
    _inherit = 'omniship.processor'

    def generate_ups_label(self, cr, uid, package, context=None):
        omni_obj = self.pool.get('omniship')
        omni_id = omni_obj.search(cr, uid, [('active', '=', True), ('carrier', '=', 'ups')], limit=1)
        if not omni_id:
            raise osv.except_osv(_('Configuration Error!'),_("Could not locate a UPS carrier integration!"))
        omni = omni_obj.browse(cr, uid, omni_id[0])
	
	self.do_shipping_request(cr, uid, omni, package, context=None)
	return True


    def get_ups_api(self, cr, uid, omni, call='confirm', context=None):
        """
        Returns API with credentials set
        """
	omni_obj = self.pool.get('omniship')
        ups_credentials = omni_obj.get_ups_credentials(
            cr, uid, omni, context)
        if not ups_credentials[0] or not ups_credentials[1] or \
            not ups_credentials[2]:
            raise osv.except_osv(('Error : '),
                ("Please check your license details for UPS account.\nSome details may be missing."))
        if call == 'confirm':
            call_method = ShipmentConfirm
        elif call == 'accept':
            call_method = ShipmentAccept
        elif call == 'void':
            call_method = ShipmentVoid
        else:
            call_method = None

        if call_method:
            try:
                return call_method(ups_credentials[0],
                                   ups_credentials[1],
                                   ups_credentials[2],
                                   ups_credentials[3],
                                   ups_credentials[4])
            except TypeError:
                ## Older PyUPS version
                return call_method(ups_credentials[0],
                                   ups_credentials[1],
                                   ups_credentials[2],
                                   ups_credentials[3])


    def _add_packages(self, cr, uid, omni, package, weight, context=None):
        """
        Adds the UPS style packages and return the XML element

        """
	picking_obj = self.pool.get('stock.picking')
	package_obj = self.pool.get('stock.out.package')

	ups_package = None
	omni_obj = self.pool.get('omniship')
        ups_uoms = omni_obj.get_ups_uoms(cr, uid, omni, context)

	#Solves a bug where weight is rejected by UPS api for being too low
	if weight < 0.5:
	    weight = 0.5

        package_type = ShipmentConfirm.packaging_type(
            Code='02')

        package_weight = ShipmentConfirm.package_weight_type(
            Weight=str(weight), Code=ups_uoms[0],
            Description='None')

	#Shipment References
	ref1 = str(12345)
	package_referencenumber1 = \
	    ShipmentConfirm.reference_type(Code='02', Value=ref1)

	#Ignore ref2 for now
#       ref2 = str(package.move_id.product_id.sku)
 #      package_referencenumber2 = \
  #         ShipmentConfirm.reference_type(Code='02', Value=ref2)


	#REVIEW: Value set to 0
        package_service_options = \
            ShipmentConfirm.package_service_options_type(
                ShipmentConfirm.insured_value_type(
                    MonetaryValue='0'))


        if package.length > 0.1 and package.width > 0.1 and package.height > 0.1:
	    length = package.length
	    width = package.width
	    height = package.height

	elif package.shape_dimension:
	    dims = package.shape_dimension
	    length = dims.length
	    width = dims.width
	    height = dims.height

        else:
	    length = 1.0
	    width = 1.0
	    height = 1.0


        package_dimension = ShipmentConfirm.dimensions_type(
	    Code=ups_uoms[1], Length=str(length),
            Height=str(height), Width=str(width),
            Description='None'
	)

        xml_package = ShipmentConfirm.package_type(
            package_type,
            package_weight,
            package_dimension,
            package_service_options,
	    package_referencenumber1)
	#    package_referencenumber2)

        shipment_service = ShipmentConfirm.shipment_service_option_type(
            SaturdayDelivery='None')

        return ([xml_package], shipment_service)


    def _add_addresses(self, cr, uid, omni, package, context=None):
        """
        Adds the UPS style addresses to the ShipmentConfirm

        """
        address_obj = self.pool.get('res.partner')

	omni_obj = self.pool.get('omniship')
        ups_shipper = omni_obj.get_ups_shipper(cr, uid, omni, context)
        #Fetch Addresses
	if package.alternate_sender_address:
	    from_addr = package.alternate_sender_address
	    to_addr = package.picking.company_id.partner_id
	else:
	    from_addr = package.picking.company_id.partner_id
	    to_addr = package.picking.partner_id

        to_address = address_obj.address_to_ups_dict(
            cr, uid, to_addr, context)
        from_address = address_obj.address_to_ups_dict(
            cr, uid, from_addr, context)
        shipper_address = address_obj.address_to_ups_dict(
            cr, uid, package.picking.company_id.partner_id, context)
        # Generating the XML Elements

        # Ship to address
        ship_to_address_elem = ShipmentConfirm.address_type(
            AddressLine1=to_address['line1'],
            AddressLine2=to_address['line2'],
            City=to_address['city'],
            PostalCode=to_address['postal_code'],
            StateProvinceCode=to_address['state_code'],
            CountryCode=to_address['country_code'],)

        # Ship from address
        ship_from_address_elem = ShipmentConfirm.address_type(
            AddressLine1=from_address['line1'],
            AddressLine2=from_address['line2'],
            City=from_address['city'],
            PostalCode=from_address['postal_code'],
            StateProvinceCode=from_address['state_code'],
            CountryCode=from_address['country_code'])


        # Shipper address
        shipper_address_elem = ShipmentConfirm.address_type(
            AddressLine1=shipper_address['line1'],
            AddressLine2=shipper_address['line2'],
            City=shipper_address['city'],
            PostalCode=shipper_address['postal_code'],
            StateProvinceCode=from_address['state_code'],
            CountryCode=shipper_address['country_code'])

        # Shipper
        shipper = ShipmentConfirm.shipper_type(
            shipper_address_elem,
            Name=shipper_address['company_name'],
            AttentionName=shipper_address['attention_name'],
            TaxIdentificationNumber=shipper_address['tin'],
            PhoneNumber=shipper_address['phone'],
            FaxNumber=shipper_address['fax'],
            EMailAddress=shipper_address['email'] or '',
            ShipperNumber=ups_shipper)

	if to_address['email'] == 'None':
	    to_address['email'] = ''

        # Ship to
        ship_to = ShipmentConfirm.ship_to_type(
            ship_to_address_elem,
            CompanyName=to_address['company_name'],
            AttentionName=to_address['attention_name'],
            TaxIdentificationNumber=to_address['tin'],
            PhoneNumber=to_address['phone'],
            FaxNumber=to_address['fax'],
            EMailAddress=to_address['email'],
            LocationId='None')

        # Ship from
        ship_from = ShipmentConfirm.ship_from_type(
            ship_from_address_elem,
            CompanyName=from_address['company_name'],
            AttentionName=from_address['attention_name'],
            TaxIdentificationNumber=from_address['tin'],
            PhoneNumber=from_address['phone'],
	    FaxNumber=from_address['fax'],
            EMailAddress=from_address['email'])
        return (shipper, ship_to, ship_from)


    def do_shipping_request(self, cr, uid, omni, package, context=None):
        """
	This method calls the UPS API, sends the ShipmentConfirm Request
	to the API and gets the total cost of shipment and tracking number.

        """

	package_obj = self.pool.get('stock.out.package')
        currency_obj = self.pool.get('res.currency')
        uom_obj = self.pool.get('product.uom')
	picking_obj = self.pool.get('stock.picking')
        ups_message_obj = self.pool.get('ups.message')
	omni_obj = self.pool.get('omniship')
        ups_shipper = omni_obj.get_ups_shipper(cr, uid, omni, context)

        payment_info_prepaid = \
            ShipmentConfirm.payment_information_prepaid_type(
                AccountNumber=ups_shipper)
        payment_info = ShipmentConfirm.payment_information_type(
            payment_info_prepaid)


        (shipper, ship_to, ship_from) = self._add_addresses(cr, uid, omni,
            package, context)

	if not package.picking.carrier_id.service:
	    raise osv.except_osv(_('Error!'),_("Delivery method has no service: %s")% package.picking.carrier_id.name)

	if not package.picking.carrier_id.service.service_code:
	    raise osv.except_osv(_('Error!'),_("The Carrier %s is not a valid UPS Shipping Method")% package.picking.carrier_id.service.name)

        service = ShipmentConfirm.service_type(
            Code=package.picking.carrier_id.service.service_code)

	#TODO Fix weight
	weight = package.weight or 1.00

	#TODO Review reference
        (packages, shipment_service) = self._add_packages(cr, uid,
            omni, package, weight, context)
        ship_confirm = ShipmentConfirm.shipment_confirm_request_type(
            shipper, ship_to, ship_from, service, payment_info,
            shipment_service, *packages,
            Description='None')

        shipment_confirm_instance = self.get_ups_api(cr, uid, omni, 'confirm', context)
	#Try to get transaction reference to work
	shipment_confirm_instance.TransactionReference = E.TransactionReference(
	    E.CustomerContext('test')
	)
	#End Transaction Reference
        try:
            response = shipment_confirm_instance.request(
                ship_confirm)
            if isinstance(response, tuple):
                request = response[0]
                response = response[1]

        except PyUPSException, error:
            raise osv.except_osv(('Error : '), ('%s' % error[0]))

        # Now store values in the register
	currency_id = currency_obj.search(cr, uid,
            [('symbol', '=', \
                response.ShipmentCharges.TotalCharges.CurrencyCode)])
     #   uom_id = uom_obj.search(cr, uid, [
      #      ('name', '=', \
       #         response.BillingWeight.UnitOfMeasurement.Code.pyval)])

        before = ShipmentConfirm.extract_digest(response)

        xml_messages = []
        package_obj.write(cr, uid, package.id,
            {
#                    'name': response.ShipmentIdentificationNumber,
 #                   'billed_weight': response.BillingWeight.Weight,
  #                  'billed_weight_uom': uom_id and uom_id[0] or False,
                    'cost': response.ShipmentCharges.\
                        TotalCharges.MonetaryValue,
     #               'total_amount_currency': currency_id and \
      #                                          currency_id[0] or False,
                'digest': ShipmentConfirm.extract_digest(response),
       #             'xml_messages': xml_messages,
        #            'state': 'confirmed'
                }, context)

#        after = package_obj.browse(cr, uid, package.id).digest

#            packages_obj.write(cr, uid,
 #               [pkg.id for pkg in shipment_record.package_det],
  #              {'state': 'confirmed'}, context)

        self.accept_price(cr, uid, omni, package, context=None)
        return True


    def accept_price(self, cr, uid, omni, package, context=None):
        '''
        This method calls the Accept Price function of the wizard .
        :return: True
        '''
	package_obj = self.pool.get('stock.out.package')
	move_obj = self.pool.get('stock.move')

        # writing image to digest so that it can be used.
        shipment_accept = ShipmentAccept.shipment_accept_request_type(\
            package.digest)
	#Accept Transaction Reference
        shipment_accept_instance = self.get_ups_api(cr, uid, omni, 'accept', context)

        shipment_accept_instance.TransactionReference = E.TransactionReference(
            E.CustomerContext('12345')
        )
        #End Transaction Reference

        try:
            response = shipment_accept_instance.request(
                shipment_accept)
            if isinstance(response, tuple):
                request = response[0]
                response = response[1]

        except PyUPSException, error:
            raise osv.except_osv(('Error : '), ('%s' % error[0]))

        packages = []
        for ups_package in response.ShipmentResults.PackageResults:
            packages.append(ups_package)
            # UPS does not give the information as to which package
            # got which label, Here we are just assuming that they
            # came in order to assign the label
 #           package_record_ids = [pkg.id for pkg in \
#                shipping_register_record.package_det]
#            assert len(package_record_ids) == len(packages)
	    label_ids = []
            image_buffer = ups_package.LabelImage.GraphicImage.pyval
            img_decoded =  base64.decodestring(image_buffer)
            image_string = cStringIO.StringIO(img_decoded)
            im = Image.open(image_string)
            rotated_image = im.rotate(90)
            box = (0, 100, 800, 1400)
            test = rotated_image.crop(box)

	    string_logo = omni.label_image

	    if not string_logo:
             #   logo_img_decoded =  base64.decodestring(string_logo)
              #  logo_image_string = cStringIO.StringIO(logo_img_decoded)
               # logo = Image.open(logo_image_string)
	        #rotated_logo = logo.rotate(180)

                images = [test]
                w = 800
                mh = 1300
                x = 0
                y = 0
                result = Image.new("1", (w, mh))
                for i in images:
                    result.paste(i, (x, y))
                    y = 1300

                file_test = StringIO()

                result.save(file_test, 'png')

#	    else:
#		raise

            tracking_number = ups_package.TrackingNumber.pyval

	    vals = {'tracking_number': tracking_number, 'name': tracking_number + '.gif', 'file': file_test.getvalue().encode('base64')}
	    package_obj.write(cr, uid, package.id, vals)

        return True


    def send_label_to_cups(self, cr, uid, img_unsaved, user_record, context=None):
	share_name = user_record.soloship_printer_id.name
	printer_host = user_record.soloship_printer_id.host

        try:
            with NamedTemporaryFile(mode='r+w', suffix='.gif') as tf:
                name = tf.name
                img_unsaved.save(name)
                #TODO: fixme
		command = ["lpr", "-H", printer_host]
		command.extend(["-o", "page-left=0", "-o", "media='4x8.5'", "-P", share_name, name])
                subprocess.call(command)

        except Exception, e:
	    print e
