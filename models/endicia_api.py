#This code is strongly based on a module written for OpenERP V6 by Openlabs
#copyright: (c) 2011 by Openlabs Technologies & Consulting (P) Ltd.

from endicia import ShippingLabelAPI, LabelRequest, RefundRequestAPI, \
    SCANFormAPI, Element
from endicia.tools import parse_response, parse_images
from endicia.exceptions import RequestError

from openerp.osv import osv, fields
from openerp.tools.translate import _

class OmnishipProcessor(osv.osv_memory):

    _inherit = 'omniship.processor'


    def generate_endicia_label(self, cr, uid, package, context=None):
        if context is None:
            context = {}

        package_obj = self.pool.get('stock.out.package')
        omni_obj = self.pool.get('omniship')
        omni_id = omni_obj.search(cr, uid, [('active', '=', True), \
		('carrier', '=', 'usps')], limit=1)
        if not omni_id:
            raise osv.except_osv(_('Configuration Error!'), \
		_("Could not locate a USPS, carrier integration!"))

	omni = omni_obj.browse(cr, uid, omni_id[0])

        self.make_label(cr, uid, omni, package, context)

     #   datas = {'ids' : context.get('active_ids',[])}
      #  datas['form'] = {}

       # return {
        #    'type': 'ir.actions.report.xml',
         #   'report_name':'package.shipping.usps.label' \
          #      if not label_wizard_data.is_apo and \
           #     package.address_id.country_id.code=='US' else \
            #    'package.shipping.usps.forms',
          #  'datas' : datas,
     #  }

	return True


    def _make_label(self, cr, uid, omni, package, context=None):

        package_obj = self.pool.get('stock.out.package')
        omni_obj = self.pool.get('omniship')
	address_obj = self.pool.get('res.partner')


        # Getting the api credentials to be used in shipping label generation
        # endicia credentials are in the format :
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = omni_obj.get_endicia_credentials(
                                                cr,
                                                uid,
						omni,
                                                context,
        )

        if not endicia_credentials[0] or not endicia_credentials[1] or \
            not endicia_credentials[2]:
            raise osv.except_osv(('Error : '),
                ("Please check the account settings for Endicia account. \nSome details may be missing."))

	#Determine if a Military Order
	apo = False
	if package.picking.partner_id.city.lower() in ['apo', 'fpo', 'dpo']:
	    apo = True

	#Determine if International Order
	#Another option in the documentation is listed as "Domestic"
	#However an attempt returned an unknown error
	if package.picking.partner_id.country_id.code != 'US':
	    mailclass = 'International'
	else:
	    mailclass = 'Priority'

        label_request = LabelRequest(
            Test=endicia_credentials[3] and 'YES' or 'NO',
            LabelType= ('International' in mailclass) and 'International' \
                or 'Priority' if apo else 'Default',
            LabelSubtype= 'Integrated' if apo \
                else package.label_sub_type or 'None',
        )

	#If a package weight is passed as 0, it is not sent in the API and could result
	#in an unknown error being returned
	if not package.weight or package.weight <= 0.4:
	    package.weight = 0.5

        shipping_label_api = ShippingLabelAPI(
                       label_request=label_request,
                       weight_oz=float(package.weight)*16,
                       partner_customer_id=package.picking.partner_id.id,
                       partner_transaction_id=package.picking.id,
                       mail_class=mailclass,
                       accountid=endicia_credentials[0],
                       requesterid=endicia_credentials[1],
                       passphrase=endicia_credentials[2],
                       test=endicia_credentials[3],
                       )

        if package.alternate_sender_address:
            from_addr = package.alternate_sender_address
            to_addr = package.picking.company_id.partner_id
        else:
            from_addr = package.picking.company_id.partner_id
            to_addr = package.picking.partner_id

        from_address = address_obj.address_to_endicia_from_address(
            cr, uid,
            from_addr,
            context)

        to_address = address_obj.address_to_endicia_to_address(
            cr, uid,
            to_addr,
            context)

        shipping_label_api.add_data(from_address.data)
        shipping_label_api.add_data(to_address.data)
        #Comment this line if not required
        shipping_label_api = self._add_items(cr, uid, omni, shipping_label_api,
                                    package, context)

        response = shipping_label_api.send_request()

        return (parse_response(response, shipping_label_api.namespace),
                    parse_images(response, shipping_label_api.namespace))


    def make_label(self, cr, uid, omni, package, context=None):
        """
        Wrapper for the make_label method
        """
        results = {}
	package_obj = self.pool.get('stock.out.package')
	omni_obj = self.pool.get('omniship')

        try:
            results, labels = self._make_label(
                    cr, uid, omni, package, context)

        except RequestError, error:
            raise osv.except_osv(
                    _('Error in generating label'),
                    _(error)
                    )
        # Do the extra bits here like saving the tracking no
        tracking_number = results.get('TrackingNumber')
        postage_paid = results.get('FinalPostage')

        # The label image is available in two elements:
        #  1. Base64LabelImage - This is abset if the label
        #       node is present
        #  2. Label - Contains one or mode elements of each part
        #
        # An attempt to save label is made at first if it exists,
        # else, the Base64LabelImage is saved
        label_ids = []
        for label in labels:
            package_obj.write(cr, uid, package.id, {
               'name': tracking_number + '.gif',
               'file': label,
	       'tracking_number': tracking_number,
	       'cost': postage_paid,
	    })

        return True


    def _add_items(self, cr, uid, omni, shipping_label_api, 
                                    package, context=None):
        '''Adding customs items/info and form descriptions to the request
        '''
        customsitems = []
        value = 0
        description = ''
	uid_obj = self.pool.get('res.users')

        country = package.picking.partner_id.country_id.code

        for move_line in package.picking.move_lines:
            customs_item_det = (
                    move_line.product_id.name,
                    move_line.product_id.list_price
            )

            # IF shipping to an APO or international
            if not country == 'US' or package.picking.partner_id.city.lower() \
		in ['apo', 'fpo', 'dpo']:

                if not customs_item_det[0] or not customs_item_det[1]:
                    raise osv.except_osv(
                    ('Error in validation'),
                        (
                        'The Selected product has no customs details'\
                        '\nAdd the details under Endicia Integration'\
                        ' tab on product page of "%s"' % move_line.product_id.name
                        )
                    )

                new_item = [
                    Element('Description',customs_item_det[0][:30]),
                    Element('Quantity', int(move_line.product_qty)),
                    Element('Weight', '1'),
                    Element('Value', customs_item_det[1]),
                    ]

                customsitems.append(Element('CustomsItem', new_item))

                shipping_label_api.add_data(
                    {
                     'CustomsInfo':[
                            Element('CustomsItems', customsitems),
                            Element('ContentsType', 'Merchandise')],
                    'CustomsCertify':'TRUE',
                    'CustomsSigner':uid_obj.browse(cr, uid, 
                        uid, context=context).name,
                    'IntegratedFormType': 'Form2976A',
                    }
                )

            value += \
                    (move_line.product_id.list_price*move_line.product_qty)

            description = description + 'Product'

#	    value = 5.00

        shipping_label_api.add_data(
                        {
                'LabelSize': 'DocTab',
                'ContentsType': 'Merchandise',
                'MailpieceShape': package.shape_dimension.value or 'Parcel',
                'Value': value,
                'Description': description[:50],
		'IncludePostage': 'TRUE',
#                'IncludePostage':package.include_postage and 'TRUE' or 'FALSE',
                 }
        )


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

        shipping_label_api.add_data(
            {
             'MailpieceDimensions': [
                 Element('Length', length),
                 Element('Width', width),
                 Element('Height', height),
              ]
            }
        )

        if package.label_sub_type and package.label_sub_type != 'None':
            shipping_label_api.add_data(
                        {
                    'IntegratedFormType':package.integrated_form_type,
                }
        )

        return shipping_label_api


    def refund_request(self, cr, uid, omni, package, context=None):
        """
        Cancels the current shipment and refunds the cost.
        """
        # Getting the api credentials to be used in refund request generation
        # endicia credentials are in the format : 
        # (account_id, requester_id, passphrase, is_test)
	package_obj = self.pool.get('stock.out.package')
	omni_obj = self.pool.get('omniship')
        endicia_credentials = omni_obj.get_endicia_credentials(
                                                cr,
                                                uid,
						omni,
                                                context)
        if not endicia_credentials[0] or not endicia_credentials[1] or \
            not endicia_credentials[2]:
            raise osv.except_osv(('Error : '),
                ("Please check the account settings for Endicia account.\nSome details may be missing."))

        pic_number = package.tracking_number

        if endicia_credentials[3]:
            test = 'Y'
        else:
            test = 'N'

        refund_request = RefundRequestAPI(
            pic_number=pic_number,
            accountid=endicia_credentials[0],
            requesterid=endicia_credentials[1],
            passphrase=endicia_credentials[2],
            test=test,
        )

        response = refund_request.send_request()
        result = parse_response(response, refund_request.namespace)

        if result['IsApproved'] == 'YES':
            refund_approved = True
        else:
            refund_approved = False

        package_obj.write(cr, uid, package.id, {
                    'refund_status': result['ErrorMsg'], 
                    'refund_approved': refund_approved, 
                    }, context=context)

        return True


    def make_scan_form(self, cr, uid, omni, package, context=None):
        """
        Generate the SCAN Form for the current shipment record
        """
        package_obj = self.pool.get('stock.out.package')
        omni_obj = self.pool.get('omniship')
        # Getting the api credentials to be used in refund request generation
        # endicia credentials are in the format : 
        # (account_id, requester_id, passphrase, is_test)
        endicia_credentials = omni_obj.get_endicia_credentials(
                                                cr,
                                                uid,
                                                context)
        if not endicia_credentials[0] or not endicia_credentials[1] or \
            not endicia_credentials[2]:
            raise osv.except_osv(('Error : '),
                ('''Please check the account settings for Endicia account.
                    \nSome details may be missing.'''))

        # tracking_no is same as PICNumber
        pic_number = package.tracking_number

        if endicia_credentials[3]:
            test = 'Y'
        else:
            test = 'N'

        scan_request = SCANFormAPI(
            pic_number=pic_number,
            accountid=endicia_credentials[0],
            requesterid=endicia_credentials[1],
            passphrase=endicia_credentials[2],
            test=test,
        )

        response = scan_request.send_request()
        result = parse_response(response, scan_request.namespace)
        scan_form = result.get('SCANForm', None)

        if not scan_form:
            raise osv.except_osv(('Error'), ('"%s"' % result.get('ErrorMsg')))
        

	#TODO: Port this code
        package_ids = package_obj.search(cr, uid,
            [('tracking_no', '=', pic_number)], context=context)

        label_ids = label_obj.create(cr, uid, {
           'name': 'SCAN'+result.get('SubmissionID') + '.gif',
           'label_image': scan_form,
           'shipping_package': package_ids[0]})

        self.write(cr, uid, ids, {'scan_form': label_ids})
        return True
