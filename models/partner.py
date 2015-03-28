import string
from endicia import FromAddress, ToAddress
from openerp.osv import osv, fields

class ResPartner(osv.osv):
    """
    Add method to return address in UPS format
    """
    _inherit = 'res.partner'
    
    def address_to_ups_dict(self, cr, uid, address, context=None):
        """
        This method creates the dictionary of all the
        details of the recipient of the package.
        These details are to be used by the UPS integration API.
        
        :return: Returns the dictionary comprising of the details
                of the package recipient.
        """

        phone = address.phone

        if phone:

            phone = "".join([char for char in phone if char in string.digits])

	#Solves bug in XML request if address contains carriage returns
        address_data = address.street.replace('\r', '\n')
        addr_lines = address_data.split('\n')

        if len(addr_lines) > 1:
            addr_line1 = addr_lines[0]
	    if address.street2:
		addr_line2 = addr_lines[1] + ' ' + address.street2
	    else:
                addr_line2 = addr_lines[1]


        else:
	    addr_line1 = address.street
            addr_line2 = address.street2

	if addr_line2 and len(addr_line2) > 35:
	    addr_line2 = addr_line2[:35]

        return {
            'line1' : addr_line1,
            'line2' : addr_line2 or ' ',
            'city' : address.city or 'None',
            'postal_code' : address.zip or 'None',
            'country_code' : address.country_id and \
                                address.country_id.code or 'None',
            'state_code' : address.state_id and \
                                address.state_id.code or 'None',
            'phone' : phone or '9999999999',
            'company_name' : address.name,
            'attention_name' : address.name,
	    'tin': 'None',
            'email' : address.email or 'noemail@noemail.com',
            'fax' : address.fax or 'None', 
        }


    def address_to_endicia_from_address(self, cr, uid, address, context=None):
        '''
            Converts partner address to Endicia Form Address.

            :param cr: Database cr
            :param uid: ID of current uid
            :param address_id: ID of record
            :param context: Context from parent method(no direct use)

            :param return: Returns instance of FromAddress
        '''

        phone = address.phone
        if phone:
            phone = "".join([char for char in phone if char in string.digits])

        #Solves bug in XML request if address contains carriage returns
        address_data = address.street.replace('\r', '\n')
        addr_lines = address_data.split('\n')

        if len(addr_lines) > 1:
            addr_line1 = addr_lines[0]
            if address.street2:
                addr_line2 = addr_lines[1] + ' ' + address.street2
            else:
                addr_line2 = addr_lines[1]


        else:
            addr_line1 = address.street
            addr_line2 = address.street2

        if addr_line2 and len(addr_line2) > 35:
            addr_line2 = addr_line2[:35]
        return FromAddress(
                     FromName = address.name,
#                     FromCompany = uid_rec.company_id.name or None,
                     ReturnAddress1 = addr_line1 or None,
                     ReturnAddress2 = addr_line2 or None,
                     ReturnAddress3 = None,
                     ReturnAddress4 = None,
                     FromCity = address.city or None,
                     FromState = address.state_id and \
                                    address.state_id.code or None,
                     FromPostalCode = address.zip or None,
                     FromPhone = phone or None,
                     FromEMail = address.email or None,
                    )


    def address_to_endicia_to_address(self, cr, uid, address, context=None):
        '''
            Converts partner address to Endicia Form Address.

            :param cr: Database cr
            :param uid: ID of current uid
            :param address_id: ID of record
            :param context: Context from parent method(no direct use)

            :param return: Returns instance of ToAddress
        '''
        phone = address.phone
        if phone:
            phone = "".join([char for char in phone if char in string.digits])
        return ToAddress(
                         ToName = address.name or None,
                         ToCompany = address.name or None,
                         ToAddress1 = address.street or None,
                         ToAddress2 = address.street2 or None,
                         ToAddress3 = None,
                         ToAddress4 = None,
                         ToCity = address.city or None,
                         ToState = address.state_id and address.state_id.code \
                             or None,
                         ToPostalCode = address.zip[:5] or None,
                         ToZIP4 = len(address.zip)==10 and address.zip[6:] or \
                            None,
                         ToCountry = address.country_id and \
                                        address.country_id.name or None,
                         ToCountryCode = address.country_id and \
                             address.country_id.code or None,
                         ToPhone = phone or '9999999999',
                         ToEMail = address.email or None,
                         )
