from unittest.mock import AsyncMock, Mock, patch

import pytest

from iso15118.evcc.states.iso15118_20_states import ACChargeLoop, PowerDelivery
from iso15118.shared.messages.enums import ControlMode, ServiceV20
from iso15118.shared.messages.iso15118_20.ac import ACChargeLoopRes
from iso15118.shared.messages.iso15118_20.common_messages import (
    ChargeProgress,
    DynamicEVPowerProfile,
    EVPowerProfile,
    EVPowerScheduleEntry,
    EVPowerScheduleEntryList,
)
from iso15118.shared.messages.iso15118_20.common_types import (
    EVSENotification,
    EVSEStatus,
    RationalNumber,
)

STATES = "iso15118.evcc.states.iso15118_20_states"


def comm_session():
    session = Mock()
    session.in_standby = False
    session.session_id = "0011223344556677"
    session.selected_energy_service.service = ServiceV20.AC
    session.control_mode = ControlMode.DYNAMIC
    session.ev_controller.continue_charging = AsyncMock(return_value=True)
    session.ev_controller.get_ac_charge_loop_params_v20 = AsyncMock(
        return_value=Mock()
    )
    return session


def response(notification):
    message = Mock(spec=ACChargeLoopRes)
    message.evse_status = EVSEStatus(
        notification_max_delay=10, evse_notification=notification
    )
    return message


def profile():
    return EVPowerProfile(
        time_anchor=0,
        entry_list=EVPowerScheduleEntryList(
            entries=[
                EVPowerScheduleEntry(
                    duration=3600, power=RationalNumber(exponent=0, value=11000)
                )
            ]
        ),
        dynamic_profile=DynamicEVPowerProfile(),
    )


async def process(state, message):
    state.check_msg_v20 = Mock(return_value=message)
    state.create_next_message = Mock()
    with patch(f"{STATES}.ACChargeLoopReq", Mock()):
        await state.process_message(message)
    return state.create_next_message


@pytest.mark.asyncio
async def test_a_pause_is_taken_as_a_standby_period():
    session = comm_session()
    state = ACChargeLoop(session)
    create = await process(state, response(EVSENotification.PAUSE))
    next_state, request = create.call_args.args[:2]
    assert next_state is PowerDelivery
    assert request.charge_progress == ChargeProgress.STANDBY
    assert session.in_standby


@pytest.mark.asyncio
async def test_a_repeated_pause_does_not_send_another_standby():
    session = comm_session()
    session.in_standby = True
    state = ACChargeLoop(session)
    create = await process(state, response(EVSENotification.PAUSE))
    assert create.call_args.args[0] is ACChargeLoop


@pytest.mark.asyncio
async def test_exit_standby_starts_charging_again():
    session = comm_session()
    session.in_standby = True
    state = ACChargeLoop(session)
    session.ev_controller.process_dynamic_se_params = AsyncMock(
        return_value=(profile(), ChargeProgress.START)
    )
    create = await process(state, response(EVSENotification.EXIT_STANDBY))
    next_state, request = create.call_args.args[:2]
    assert next_state is PowerDelivery
    assert request.charge_progress == ChargeProgress.START
    assert not session.in_standby


@pytest.mark.asyncio
async def test_exit_standby_without_a_standby_changes_nothing():
    session = comm_session()
    state = ACChargeLoop(session)
    create = await process(state, response(EVSENotification.EXIT_STANDBY))
    assert create.call_args.args[0] is ACChargeLoop
